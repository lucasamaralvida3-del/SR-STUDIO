from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from srstudio.app.design import COLORS, FONT
from srstudio.app.image_bank_view import ImageBankView


class BatchImageBankView(ImageBankView):
    """Fast multi-select review layer for the SR image bank."""

    def __init__(self, *args, **kwargs) -> None:
        self._delete_dialog: tk.Toplevel | None = None
        self._verify_dialog: tk.Toplevel | None = None
        self._verify_photo: ImageTk.PhotoImage | None = None
        self._verify_ids: list[str] = []
        self._verify_index = 0
        self._verify_approved = 0
        self._verify_rejected = 0
        self._verify_skipped = 0
        self._status_after: str | None = None
        super().__init__(*args, **kwargs)
        self._install_shortcuts()

    def _build(self) -> None:
        super()._build()
        self.tree.configure(selectmode="extended")

        children = self.winfo_children()
        body = children[-1] if children else None
        self.batch_bar = tk.Frame(
            self,
            bg=COLORS.surface,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        if body is not None:
            self.batch_bar.pack(fill="x", before=body, pady=(0, 10))
        else:
            self.batch_bar.pack(fill="x", pady=(0, 10))

        left = tk.Frame(self.batch_bar, bg=COLORS.surface)
        left.pack(side="left", padx=12, pady=8)
        ttk.Button(left, text="☑  Selecionar todas", command=self._select_all_visible).pack(side="left", padx=(0, 6))
        ttk.Button(left, text="☐  Desmarcar todas", command=self._clear_selection).pack(side="left")

        self.batch_count = tk.Label(
            self.batch_bar,
            text="0 selecionadas",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8, "bold"),
        )
        self.batch_count.pack(side="left", padx=14)

        right = tk.Frame(self.batch_bar, bg=COLORS.surface)
        right.pack(side="right", padx=12, pady=8)
        ttk.Button(
            right,
            text="▶  VERIFICAR",
            style="Secondary.TButton",
            command=self._start_verification,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            right,
            text="A  APROVAR SELECIONADAS",
            style="Primary.TButton",
            command=self._approve_selected,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            right,
            text="R  RECUSAR / APAGAR",
            command=self._request_delete_selected,
        ).pack(side="left")

        self.tree.bind("<<TreeviewSelect>>", self._batch_selection_changed, add="+")

    def _batch_selection_changed(self, _event=None) -> None:
        self._update_batch_count()

    def _selected_ids(self) -> list[str]:
        return [asset_id for asset_id in self.tree.selection() if asset_id in self._rows]

    def _update_batch_count(self) -> None:
        if hasattr(self, "batch_count"):
            count = len(self._selected_ids())
            self.batch_count.configure(text=f"{count} selecionada{'s' if count != 1 else ''}")

    def _select_all_visible(self, _event=None) -> str:
        ids = list(self.tree.get_children())
        if ids:
            self.tree.selection_set(ids)
            self.tree.focus(ids[0])
            self.tree.see(ids[0])
            self._selection_changed()
        self._update_batch_count()
        return "break"

    def _clear_selection(self, _event=None) -> str:
        if self._delete_dialog is not None and self._delete_dialog.winfo_exists():
            self._cancel_delete()
            return "break"
        if self._verify_dialog is not None and self._verify_dialog.winfo_exists():
            self._close_verification()
            return "break"
        self.tree.selection_remove(self.tree.selection())
        self._update_batch_count()
        self._show_empty_detail()
        return "break"

    def _approve_selected(self, _event=None) -> str:
        ids = self._selected_ids()
        if not ids:
            return "break"
        for asset_id in ids:
            self.library.set_review_status(asset_id, "accepted")
        self._notify_changed()
        self._refresh()
        self._flash_batch_status(f"✓ {len(ids)} imagem(ns) aprovada(s)")
        return "break"

    def _request_delete_selected(self, _event=None) -> str:
        ids = self._selected_ids()
        if not ids:
            return "break"
        if self._delete_dialog is not None and self._delete_dialog.winfo_exists():
            self._confirm_delete()
            return "break"
        self._open_delete_dialog(ids)
        return "break"

    def _open_delete_dialog(self, asset_ids: list[str]) -> None:
        dialog = tk.Toplevel(self)
        self._delete_dialog = dialog
        dialog.title("Recusar e apagar imagens")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg=COLORS.surface)
        dialog.protocol("WM_DELETE_WINDOW", self._cancel_delete)

        tk.Label(
            dialog,
            text="APAGAR IMAGENS SELECIONADAS?",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 11, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 6))
        tk.Label(
            dialog,
            text=(
                f"{len(asset_ids)} imagem(ns) serão removidas do Banco de Imagens e do armazenamento local.\n"
                "Esta ação não pode ser desfeita."
            ),
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 9),
            justify="left",
        ).pack(anchor="w", padx=22, pady=(0, 14))
        hint = tk.Label(
            dialog,
            text="Pressione R novamente para confirmar · Esc para cancelar",
            bg="#FFF4DE",
            fg="#8B5A00",
            font=(FONT["family"], 8, "bold"),
            padx=10,
            pady=8,
        )
        hint.pack(fill="x", padx=22, pady=(0, 14))

        actions = tk.Frame(dialog, bg=COLORS.surface)
        actions.pack(fill="x", padx=22, pady=(0, 20))
        ttk.Button(actions, text="Cancelar  [Esc]", command=self._cancel_delete).pack(side="right")
        ttk.Button(
            actions,
            text="R  APAGAR AGORA",
            style="Primary.TButton",
            command=self._confirm_delete,
        ).pack(side="right", padx=(0, 8))

        dialog.bind("<KeyPress-r>", lambda _e: self._confirm_delete())
        dialog.bind("<KeyPress-R>", lambda _e: self._confirm_delete())
        dialog.bind("<Return>", lambda _e: self._confirm_delete())
        dialog.bind("<Escape>", lambda _e: self._cancel_delete())
        dialog.update_idletasks()
        parent = self.winfo_toplevel()
        x = parent.winfo_rootx() + max(20, (parent.winfo_width() - dialog.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(20, (parent.winfo_height() - dialog.winfo_reqheight()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.focus_force()

    def _confirm_delete(self) -> str:
        ids = self._selected_ids()
        count = self._delete_assets(ids)
        self._close_delete_dialog()
        self._notify_changed()
        self._refresh()
        self._flash_batch_status(f"✕ {count} imagem(ns) removida(s)")
        return "break"

    def _cancel_delete(self) -> str:
        self._close_delete_dialog()
        return "break"

    def _close_delete_dialog(self) -> None:
        dialog = self._delete_dialog
        self._delete_dialog = None
        if dialog is not None and dialog.winfo_exists():
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

    def _delete_assets(self, asset_ids: list[str]) -> int:
        index = self.library._load()
        removed_paths: set[str] = set()
        removed = 0
        for asset_id in asset_ids:
            data = index.pop(asset_id, None)
            if data is None:
                continue
            path = str(data.get("path") or "")
            if path:
                removed_paths.add(path)
            removed += 1
        self.library._save(index)

        remaining_paths = {str(data.get("path") or "") for data in index.values()}
        for value in removed_paths - remaining_paths:
            path = Path(value)
            try:
                if path.exists() and self.library.root in path.parents:
                    path.unlink()
            except OSError:
                pass
        return removed

    def _start_verification(self) -> str:
        ids = self._selected_ids()
        if not ids:
            self._flash_batch_status("Selecione pelo menos uma imagem para verificar")
            return "break"
        if self._verify_dialog is not None and self._verify_dialog.winfo_exists():
            self._verify_dialog.focus_force()
            return "break"

        self._verify_ids = list(ids)
        self._verify_index = 0
        self._verify_approved = 0
        self._verify_rejected = 0
        self._verify_skipped = 0

        dialog = tk.Toplevel(self)
        self._verify_dialog = dialog
        dialog.title("Verificar imagens selecionadas")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.minsize(760, 650)
        dialog.geometry("880x760")
        dialog.configure(bg=COLORS.bg)
        dialog.protocol("WM_DELETE_WINDOW", self._close_verification)

        header = tk.Frame(dialog, bg=COLORS.surface)
        header.pack(fill="x")
        title_wrap = tk.Frame(header, bg=COLORS.surface)
        title_wrap.pack(side="left", fill="x", expand=True, padx=22, pady=16)
        tk.Label(
            title_wrap,
            text="VERIFICAÇÃO DO BANCO DE IMAGENS",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 12, "bold"),
        ).pack(anchor="w")
        self._verify_progress_label = tk.Label(
            title_wrap,
            text="",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 9),
        )
        self._verify_progress_label.pack(anchor="w", pady=(3, 0))
        ttk.Button(header, text="Fechar", command=self._close_verification).pack(side="right", padx=22, pady=16)

        self._verify_progress = ttk.Progressbar(dialog, mode="determinate", maximum=max(1, len(ids)))
        self._verify_progress.pack(fill="x", padx=22, pady=(12, 8))

        content = tk.Frame(dialog, bg=COLORS.bg)
        content.pack(fill="both", expand=True, padx=22, pady=(4, 12))
        preview_card = tk.Frame(
            content,
            bg=COLORS.surface,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        preview_card.pack(fill="both", expand=True)
        self._verify_preview = tk.Label(
            preview_card,
            text="SEM PRÉVIA",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], 10, "bold"),
        )
        self._verify_preview.pack(fill="both", expand=True, padx=14, pady=(14, 10))

        info = tk.Frame(preview_card, bg=COLORS.surface)
        info.pack(fill="x", padx=18, pady=(0, 14))
        self._verify_name = tk.Label(
            info,
            text="",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 14, "bold"),
            justify="left",
            anchor="w",
            wraplength=760,
        )
        self._verify_name.pack(fill="x")
        self._verify_meta = tk.Label(
            info,
            text="",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 9),
            justify="left",
            anchor="w",
            wraplength=760,
        )
        self._verify_meta.pack(fill="x", pady=(5, 0))
        self._verify_warning = tk.Label(
            info,
            text="",
            bg="#FFF4DE",
            fg="#8B5A00",
            font=(FONT["family"], 9, "bold"),
            justify="left",
            anchor="w",
            wraplength=760,
            padx=10,
            pady=8,
        )

        actions = tk.Frame(dialog, bg=COLORS.surface)
        actions.pack(fill="x", padx=22, pady=(0, 18))
        ttk.Button(actions, text="←  VOLTAR", command=self._verify_back).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="PULAR", command=self._verify_skip).pack(side="left")
        ttk.Button(
            actions,
            text="R  RECUSAR",
            command=self._verify_reject,
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            actions,
            text="A  APROVAR",
            style="Primary.TButton",
            command=self._verify_approve,
        ).pack(side="right")

        dialog.bind("<KeyPress-a>", lambda _e: self._verify_approve())
        dialog.bind("<KeyPress-A>", lambda _e: self._verify_approve())
        dialog.bind("<KeyPress-r>", lambda _e: self._verify_reject())
        dialog.bind("<KeyPress-R>", lambda _e: self._verify_reject())
        dialog.bind("<KeyPress-s>", lambda _e: self._verify_skip())
        dialog.bind("<KeyPress-S>", lambda _e: self._verify_skip())
        dialog.bind("<Left>", lambda _e: self._verify_back())
        dialog.bind("<Escape>", lambda _e: self._close_verification())
        dialog.focus_force()
        self._render_verify_current()
        return "break"

    def _current_verify_id(self) -> str:
        if 0 <= self._verify_index < len(self._verify_ids):
            return self._verify_ids[self._verify_index]
        return ""

    def _render_verify_current(self) -> None:
        asset_id = self._current_verify_id()
        if not asset_id:
            self._finish_verification()
            return
        index = self.library._load()
        data = index.get(asset_id)
        if data is None:
            self._advance_verification()
            return
        asset = self.library._asset(data)

        total = len(self._verify_ids)
        position = self._verify_index + 1
        self._verify_progress_label.configure(
            text=(
                f"Imagem {position} de {total}  ·  "
                f"✓ {self._verify_approved} aprovadas  ·  "
                f"✕ {self._verify_rejected} recusadas  ·  "
                f"↷ {self._verify_skipped} puladas"
            )
        )
        self._verify_progress.configure(value=self._verify_index)
        self._verify_name.configure(text=asset.product_name or asset.original_name or "Produto sem nome")
        source = asset.source_file or asset.source
        self._verify_meta.configure(
            text=(
                f"Confiança {round(asset.confidence * 100)}% · {asset.width}×{asset.height} · "
                f"Origem: {source}"
            )
        )

        reason = asset.metadata.get("review_reason")
        if reason == "same_image_multiple_products":
            names = asset.metadata.get("conflicting_product_names") or ()
            text = "⚠ Esta imagem apareceu em produtos diferentes"
            if names:
                text += ":\n" + "\n".join(f"• {value}" for value in names)
            self._verify_warning.configure(text=text)
            self._verify_warning.pack(fill="x", pady=(10, 0))
        else:
            self._verify_warning.pack_forget()

        self._verify_photo = None
        try:
            with Image.open(asset.path) as opened:
                image = opened.convert("RGBA")
            image.thumbnail((760, 440), Image.Resampling.LANCZOS)
            self._verify_photo = ImageTk.PhotoImage(image, master=self._verify_dialog)
            self._verify_preview.configure(image=self._verify_photo, text="")
        except (OSError, ValueError):
            self._verify_preview.configure(image="", text="SEM PRÉVIA")

    def _verify_approve(self) -> str:
        asset_id = self._current_verify_id()
        if not asset_id:
            return "break"
        try:
            self.library.set_review_status(asset_id, "accepted")
            self._verify_approved += 1
        except KeyError:
            pass
        self._notify_changed()
        self._advance_verification()
        return "break"

    def _verify_reject(self) -> str:
        asset_id = self._current_verify_id()
        if not asset_id:
            return "break"
        removed = self._delete_assets([asset_id])
        if removed:
            self._verify_rejected += 1
        self._notify_changed()
        self._advance_verification()
        return "break"

    def _verify_skip(self) -> str:
        if not self._current_verify_id():
            return "break"
        self._verify_skipped += 1
        self._advance_verification()
        return "break"

    def _verify_back(self) -> str:
        if self._verify_index <= 0:
            return "break"
        self._verify_index -= 1
        self._render_verify_current()
        return "break"

    def _advance_verification(self) -> None:
        self._verify_index += 1
        if self._verify_index >= len(self._verify_ids):
            self._finish_verification()
        else:
            self._render_verify_current()

    def _finish_verification(self) -> None:
        approved = self._verify_approved
        rejected = self._verify_rejected
        skipped = self._verify_skipped
        total = len(self._verify_ids)
        dialog = self._verify_dialog
        if dialog is None or not dialog.winfo_exists():
            return

        for child in dialog.winfo_children():
            child.destroy()
        dialog.configure(bg=COLORS.surface)
        wrap = tk.Frame(dialog, bg=COLORS.surface)
        wrap.pack(fill="both", expand=True, padx=36, pady=36)
        tk.Label(
            wrap,
            text="✓",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 34, "bold"),
        ).pack(pady=(40, 8))
        tk.Label(
            wrap,
            text="REVISÃO CONCLUÍDA",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 16, "bold"),
        ).pack()
        tk.Label(
            wrap,
            text=(
                f"{total} imagem(ns) verificadas\n\n"
                f"✓ {approved} aprovadas\n"
                f"✕ {rejected} recusadas e removidas\n"
                f"↷ {skipped} puladas"
            ),
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 10),
            justify="center",
        ).pack(pady=(12, 22))
        ttk.Button(
            wrap,
            text="CONCLUIR",
            style="Primary.TButton",
            command=self._close_verification,
        ).pack()
        self._refresh()

    def _close_verification(self) -> str:
        dialog = self._verify_dialog
        self._verify_dialog = None
        self._verify_photo = None
        if dialog is not None and dialog.winfo_exists():
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
        self._refresh()
        return "break"

    def _review(self, asset_id: str, status: str) -> None:
        if status == "rejected":
            if asset_id in self._rows:
                self.tree.selection_set(asset_id)
                self.tree.focus(asset_id)
            self._request_delete_selected()
            return
        if asset_id in self._rows:
            selected = self._selected_ids()
            if len(selected) > 1:
                self._approve_selected()
                return
        super()._review(asset_id, status)
        self._update_batch_count()

    def _flash_batch_status(self, message: str) -> None:
        if not hasattr(self, "batch_count"):
            return
        self.batch_count.configure(text=message, fg=COLORS.text)
        if self._status_after is not None:
            try:
                self.after_cancel(self._status_after)
            except tk.TclError:
                pass
        self._status_after = self.after(2200, self._restore_batch_count)

    def _restore_batch_count(self) -> None:
        self._status_after = None
        if hasattr(self, "batch_count"):
            self.batch_count.configure(fg=COLORS.text_muted)
        self._update_batch_count()

    def _install_shortcuts(self) -> None:
        top = self.winfo_toplevel()
        top.bind("<KeyPress-a>", self._key_approve, add="+")
        top.bind("<KeyPress-A>", self._key_approve, add="+")
        top.bind("<KeyPress-r>", self._key_reject, add="+")
        top.bind("<KeyPress-R>", self._key_reject, add="+")
        top.bind("<Control-a>", self._key_select_all, add="+")
        top.bind("<Control-A>", self._key_select_all, add="+")
        top.bind("<Escape>", self._key_escape, add="+")

    def _shortcut_allowed(self, event) -> bool:
        if not self.winfo_ismapped():
            return False
        widget = getattr(event, "widget", None)
        return not isinstance(widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))

    def _key_approve(self, event) -> str | None:
        if self._verify_dialog is not None and self._verify_dialog.winfo_exists():
            return "break"
        if self._delete_dialog is not None and self._delete_dialog.winfo_exists():
            return None
        if self._shortcut_allowed(event):
            return self._approve_selected()
        return None

    def _key_reject(self, event) -> str | None:
        if self._verify_dialog is not None and self._verify_dialog.winfo_exists():
            return "break"
        if self._delete_dialog is not None and self._delete_dialog.winfo_exists():
            return self._confirm_delete()
        if self._shortcut_allowed(event):
            return self._request_delete_selected()
        return None

    def _key_select_all(self, event) -> str | None:
        if self._verify_dialog is not None and self._verify_dialog.winfo_exists():
            return "break"
        if self._shortcut_allowed(event):
            return self._select_all_visible()
        return None

    def _key_escape(self, event) -> str | None:
        if self._verify_dialog is not None and self._verify_dialog.winfo_exists():
            return "break"
        if self._delete_dialog is not None and self._delete_dialog.winfo_exists():
            return self._cancel_delete()
        if self._shortcut_allowed(event):
            return self._clear_selection()
        return None
