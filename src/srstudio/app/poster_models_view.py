from __future__ import annotations

import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from srstudio.app.design import COLORS, FONT
from srstudio.posters.catalog import PosterModelCatalog, PosterModelEntry


class PosterModelsView(tk.Frame):
    """Professional library for Promotion/Wholesale print models."""

    def __init__(
        self,
        master: tk.Misc,
        catalog: PosterModelCatalog,
        on_use: Callable[[PosterModelEntry], object] | None = None,
        toast=None,
    ) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.pack(fill="both", expand=True)
        self.catalog = catalog
        self.on_use = on_use
        self.toast = toast
        self._entries: dict[str, PosterModelEntry] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS.bg)
        header.pack(fill="x", padx=26, pady=(22, 12))
        tk.Label(
            header,
            text="Modelos de Cartaz",
            bg=COLORS.bg,
            fg=COLORS.text,
            font=(FONT["family"], 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Oficiais SR, cópias originais protegidas, modelos personalizados e histórico de versões.",
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["body"]),
        ).pack(anchor="w", pady=(3, 0))

        actions = tk.Frame(
            self,
            bg=COLORS.surface,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        actions.pack(fill="x", padx=26, pady=(0, 12))
        ttk.Button(actions, text="⟳ Reindexar modelos", style="Primary.TButton", command=self._reindex).pack(
            side="left", padx=(12, 6), pady=10
        )
        ttk.Button(actions, text="＋ Importar PPTX", style="Ghost.TButton", command=self._import_custom).pack(
            side="left", padx=6, pady=10
        )
        ttk.Button(actions, text="↺ Restaurar originais", style="Ghost.TButton", command=self._restore).pack(
            side="left", padx=6, pady=10
        )
        ttk.Button(actions, text="▣ Abrir pasta", style="Ghost.TButton", command=self._open_folder).pack(
            side="left", padx=6, pady=10
        )
        self.summary_label = tk.Label(
            actions,
            text="",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"], "bold"),
        )
        self.summary_label.pack(side="right", padx=14)

        body = tk.Frame(self, bg=COLORS.bg)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 18))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        list_card = tk.Frame(body, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        list_head = tk.Frame(list_card, bg=COLORS.surface)
        list_head.pack(fill="x", padx=14, pady=(12, 8))
        tk.Label(
            list_head,
            text="Biblioteca instalada",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 12, "bold"),
        ).pack(side="left")
        self.filter_var = tk.StringVar(value="Todos")
        filter_box = ttk.Combobox(
            list_head,
            textvariable=self.filter_var,
            state="readonly",
            width=18,
            values=("Todos", "Oficiais", "Originais", "Personalizados", "Versões"),
        )
        filter_box.pack(side="right")
        filter_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        table_shell = tk.Frame(list_card, bg=COLORS.surface)
        table_shell.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        columns = ("name", "group", "kind", "variant", "file")
        self.tree = ttk.Treeview(table_shell, columns=columns, show="headings", selectmode="browse")
        headers = {
            "name": ("Modelo", 245),
            "group": ("Origem", 105),
            "kind": ("Módulo", 90),
            "variant": ("Tipo", 125),
            "file": ("Arquivo", 230),
        }
        for key, (label, width) in headers.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=65, stretch=key in {"name", "file"})
        scroll = ttk.Scrollbar(table_shell, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_details())
        self.tree.bind("<Double-1>", lambda _e: self._use_selected())

        detail = tk.Frame(body, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        detail.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        tk.Label(
            detail,
            text="Modelo selecionado",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(15, 4))
        self.detail_title = tk.Label(
            detail,
            text="Selecione um modelo",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 15, "bold"),
            wraplength=390,
            justify="left",
        )
        self.detail_title.pack(anchor="w", padx=16, pady=(8, 3))
        self.detail_meta = tk.Label(
            detail,
            text="",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
            justify="left",
            anchor="nw",
            wraplength=390,
        )
        self.detail_meta.pack(fill="x", padx=16, pady=(2, 14))
        self.use_button = ttk.Button(detail, text="Usar neste módulo", style="Primary.TButton", command=self._use_selected)
        self.use_button.pack(fill="x", padx=16, pady=(0, 8))
        ttk.Button(detail, text="Abrir local do arquivo", style="Ghost.TButton", command=self._open_selected).pack(
            fill="x", padx=16, pady=(0, 8)
        )
        tk.Label(
            detail,
            text=(
                "Proteção ativa\n\n"
                "• Atualizações do Studio não apagam Personalizados.\n"
                "• Originais são recriados a partir dos modelos oficiais.\n"
                "• Ao substituir um Personalizado, a versão anterior vai para Versões.\n"
                "• Se o catálogo quebrar, Reindexar reconstrói a lista pelos arquivos existentes."
            ),
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
            justify="left",
            anchor="nw",
            wraplength=390,
            padx=12,
            pady=12,
        ).pack(fill="x", padx=16, pady=(10, 16))

    def refresh(self) -> None:
        entries = self.catalog.reindex()
        selected_filter = self.filter_var.get() if hasattr(self, "filter_var") else "Todos"
        if selected_filter != "Todos":
            entries = [item for item in entries if item.group == selected_filter]
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._entries.clear()
        for index, entry in enumerate(entries):
            item_id = f"model-{index}"
            self._entries[item_id] = entry
            module = "Atacado" if entry.kind.value == "wholesale" else "Promoções"
            self.tree.insert(
                "",
                "end",
                iid=item_id,
                values=(entry.name, entry.group, module, self._variant_label(entry.variant), entry.filename),
            )
        summary = self.catalog.summary()
        self.summary_label.configure(
            text=(
                f"{summary.get('Oficiais', 0)} oficiais  ·  "
                f"{summary.get('Personalizados', 0)} personalizados  ·  "
                f"{summary.get('Versões', 0)} versões"
            )
        )
        if self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
            self._show_details()
        else:
            self.detail_title.configure(text="Nenhum modelo encontrado")
            self.detail_meta.configure(text="Use Reindexar modelos ou Restaurar originais.")

    def _selected(self) -> PosterModelEntry | None:
        selected = self.tree.selection()
        return self._entries.get(selected[0]) if selected else None

    def _show_details(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        module = "Cartazes de Atacado" if entry.kind.value == "wholesale" else "Cartazes de Promoção"
        protection = "somente leitura" if entry.read_only else "editável / protegido por backup"
        recommended = "\nRECOMENDADO" if entry.recommended else ""
        self.detail_title.configure(text=entry.name)
        self.detail_meta.configure(
            text=(
                f"{module}\n"
                f"Origem: {entry.group}\n"
                f"Tipo: {self._variant_label(entry.variant)}\n"
                f"Arquivo: {entry.filename}\n"
                f"Tamanho: {entry.size / 1024:.1f} KB\n"
                f"Proteção: {protection}{recommended}\n\n"
                f"{entry.path}"
            )
        )
        self.use_button.configure(state="disabled" if entry.group == PosterModelCatalog.GROUP_VERSION else "normal")

    def _use_selected(self) -> None:
        entry = self._selected()
        if entry is None or entry.group == PosterModelCatalog.GROUP_VERSION:
            return
        if self.on_use is not None:
            self.on_use(entry)

    def _reindex(self) -> None:
        self.catalog.reindex()
        self.refresh()
        self._notify("Catálogo reconstruído a partir dos arquivos existentes.", "success")

    def _restore(self) -> None:
        copied = self.catalog.restore_originals()
        self.catalog.reindex()
        self.refresh()
        self._notify(f"Originais restaurados: {copied} arquivo(s).", "success")

    def _import_custom(self) -> None:
        path = filedialog.askopenfilename(
            title="Importar modelo de cartaz",
            filetypes=[("Modelo PowerPoint", "*.pptx"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            entry = self.catalog.install_custom(path)
        except Exception as exc:
            messagebox.showerror("Modelos", f"Não foi possível importar o modelo.\n\n{exc}")
            return
        self.filter_var.set("Personalizados")
        self.refresh()
        self._notify(f"Modelo personalizado instalado: {entry.name}", "success")

    def _open_folder(self) -> None:
        self._open_path(self.catalog.root)

    def _open_selected(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        self._open_path(Path(entry.path).parent)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif shutil_which("open"):
                subprocess.Popen(["open", str(path)])
            elif shutil_which("xdg-open"):
                subprocess.Popen(["xdg-open", str(path)])
        except OSError:
            return

    def _notify(self, message: str, tone: str) -> None:
        if self.toast is not None:
            self.toast.show(message, tone, 4200)

    @staticmethod
    def _variant_label(value: str) -> str:
        labels = {
            "atacado": "Atacado",
            "venda": "Venda",
            "1_preco": "1 preço",
            "1_preco_limite": "1 preço + limite",
            "2_precos": "2 preços",
            "2_precos_limite": "2 preços + limite",
            "clube_exclusivo": "Clube Exclusivo",
            "clube_exclusivo_limite": "Clube + limite",
            "personalizado": "Personalizado",
            "versao": "Backup",
        }
        return labels.get(value, value.replace("_", " ").title())


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)
