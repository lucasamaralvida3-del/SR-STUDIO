from __future__ import annotations

from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import srstudio.app.advanced_posters as advanced
import srstudio.app.cartazes_productivity as cartazes_productivity
import srstudio.app.responsive_posters as responsive
from srstudio.app.cloud_image_bank_view import CloudImageBankView
from srstudio.app.graphics2_merge_dialog import ask_graphics2_merge_resolutions
from srstudio.app.layout_corpus_view import LayoutCorpusView
from srstudio.app.professional import _show_splash
from srstudio.graphics2.full_studio_bridge import launch_graphics_source, launch_studio_project
from srstudio.graphics2.saved_merge import analyze_saved_session_merge, resolve_saved_session_merge
from srstudio.graphics2.studio_bridge import sync_saved_session_to_project
from srstudio.images.cloud_sync import ImageBankCloudSync
from srstudio.posters import PosterKind


class SRStudioTurboPosters(responsive.SRStudioResponsivePosters):
    """Official SR Studio shell with Studio de Encartes G2 as the only editor route."""

    def __init__(self) -> None:
        super().__init__()
        self._image_bank_sync_active = False
        self._image_bank_cloud = ImageBankCloudSync(
            self.image_library,
            self.data_dir / "image-bank-cloud",
        )
        self.after(900, self._start_image_bank_cloud_sync)

    def _start_image_bank_cloud_sync(self) -> None:
        if self._image_bank_sync_active:
            return
        self._image_bank_sync_active = True
        if hasattr(self, "sidebar_status"):
            self.sidebar_status.configure(text="Banco SR · verificando...")

        def worker() -> None:
            result = self._image_bank_cloud.sync()
            self.after(0, lambda: self._finish_image_bank_cloud_sync(result))

        threading.Thread(target=worker, name="sr-image-bank-cloud-sync", daemon=True).start()

    def _finish_image_bank_cloud_sync(self, result) -> None:
        self._image_bank_sync_active = False
        if hasattr(self, "sidebar_status"):
            if result.state == "offline":
                self.sidebar_status.configure(text="Banco SR offline · cache local")
            else:
                self.sidebar_status.configure(
                    text=f"Banco SR v{result.remote_version or result.local_version} · {result.total} imagens"
                )
        if result.downloaded:
            self.toast.show(
                f"Banco de Imagens atualizado · {result.downloaded} nova(s) imagem(ns).",
                "success",
                4200,
            )

    def navigate(self, name: str) -> None:
        # The official product has one Encartes destination. Intercept it before
        # inherited Tk editor factories can instantiate any historical editor.
        if name == "Encartes Studio":
            self._set_active_navigation(name)
            self._clear()
            self._show_graphics2_studio_entrypoint()
            return

        super().navigate(name)
        if name == "Banco de Imagens":
            self._clear()
            CloudImageBankView(
                self.content,
                self.image_library,
                self._image_bank_cloud,
                on_changed=self._mark_changed,
            )
            return
        if name != "Modelos":
            return
        self._clear()
        LayoutCorpusView(
            self.content,
            self.project,
            self.layout_corpus,
            self.templates,
            on_changed=self._mark_changed,
            on_open_encartes=lambda: self.navigate("Encartes Studio"),
            on_train=self.train_canva_library,
        )

    def _set_active_navigation(self, name: str) -> None:
        """Keep the inherited shell navigation state coherent for an override."""

        self._active_nav = name
        for label, button in self.nav_buttons.items():
            active = label == name
            try:
                button.configure(
                    bg="#173D72" if active else "#102A4D",
                    fg="white" if active else "#D5E3F5",
                )
                self.nav_indicators[label].configure(bg="#77A7FF" if active else "#102A4D")
            except (KeyError, tk.TclError):
                pass
        if hasattr(self, "topbar_title"):
            self.topbar_title.configure(text="Studio de Encartes")
        if hasattr(self, "topbar_subtitle"):
            self.topbar_subtitle.configure(text="Graphics Engine 2 · importação, edição e exportação")

    def _show_graphics2_studio_entrypoint(self) -> None:
        """Launch the only Studio de Encartes destination: Graphics Engine 2."""

        result = launch_studio_project(self.project, self.data_dir)
        self._show_graphics2_launch_result(result, retry=self._show_graphics2_studio_entrypoint)

    @staticmethod
    def _g2_action_button(parent, title: str, detail: str, command, *, primary: bool = False) -> tk.Frame:
        bg = "#0F5BD8" if primary else "#F8FAFC"
        fg = "white" if primary else "#0F172A"
        muted = "#D9E8FF" if primary else "#64748B"
        border = "#0F5BD8" if primary else "#D9E2EF"
        card = tk.Frame(parent, bg=bg, highlightbackground=border, highlightthickness=1, cursor="hand2")
        heading = tk.Label(
            card,
            text=title,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        heading.pack(anchor="w", padx=16, pady=(14, 3))
        description = tk.Label(
            card,
            text=detail,
            bg=bg,
            fg=muted,
            font=("Segoe UI", 8),
            justify="left",
            wraplength=260,
            cursor="hand2",
        )
        description.pack(anchor="w", padx=16, pady=(0, 14))
        for widget in (card, heading, description):
            widget.bind("<Button-1>", lambda _event: command())
        return card

    def _choose_graphics2_pptx(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Importar Canva / PPTX no Studio de Encartes G2",
            filetypes=[("PowerPoint / Canva", "*.pptx"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self._launch_graphics2_source(Path(path))

    def _choose_graphics2_project(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Abrir projeto do Studio de Encartes G2",
            filetypes=[("Projeto SR Scene 2", "*.srscene *.zip"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self._launch_graphics2_source(Path(path))

    def _launch_graphics2_source(self, source: Path) -> None:
        result = launch_graphics_source(source, self.data_dir)
        self._show_graphics2_launch_result(result, retry=lambda: self._launch_graphics2_source(source))

    def _launch_current_project_in_graphics2(self) -> None:
        result = launch_studio_project(self.project, self.data_dir)
        self._show_graphics2_launch_result(result, retry=self._launch_current_project_in_graphics2)

    def _show_graphics2_launch_result(self, result, *, retry=None) -> None:
        if result.launched:
            self.toast.show(result.message, "success", 5600)
            return
        self.toast.show("Não foi possível iniciar o Studio de Encartes G2", "danger", 9000)
        self._show_graphics2_launch_error(result, retry=retry)

    def _show_graphics2_launch_error(self, result, *, retry=None) -> None:
        existing = getattr(self, "_g2_launch_error_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.destroy()
            except tk.TclError:
                pass

        dialog = tk.Toplevel(self)
        self._g2_launch_error_dialog = dialog
        dialog.title("Studio de Encartes G2 — erro")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(bg="#F8FAFC")

        body = tk.Frame(dialog, bg="#F8FAFC", padx=24, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="Não foi possível iniciar o Studio de Encartes G2.",
            bg="#F8FAFC",
            fg="#991B1B",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            body,
            text="O Studio de Encartes não foi substituído por outro editor. Corrija a falha do G2 ou tente novamente.",
            bg="#F8FAFC",
            fg="#475569",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=560,
        ).pack(anchor="w", pady=(8, 14))

        detail = str(result.message or "Falha desconhecida ao iniciar o G2.")
        summary = tk.Label(
            body,
            text=detail.splitlines()[0],
            bg="#FFF1F2",
            fg="#7F1D1D",
            font=("Segoe UI", 9),
            justify="left",
            wraplength=560,
            padx=12,
            pady=10,
        )
        summary.pack(fill="x")

        actions = tk.Frame(body, bg="#F8FAFC")
        actions.pack(fill="x", pady=(16, 0))

        def try_again() -> None:
            dialog.destroy()
            if retry is not None:
                self.after(50, retry)

        def show_details() -> None:
            details = tk.Toplevel(dialog)
            details.title("Detalhes — Studio de Encartes G2")
            details.transient(dialog)
            details.geometry("760x460")
            text = tk.Text(details, wrap="word", font=("Consolas", 9), padx=12, pady=12)
            text.pack(fill="both", expand=True)
            text.insert("1.0", detail)
            text.configure(state="disabled")

        retry_button = tk.Button(
            actions,
            text="Tentar novamente",
            command=try_again,
            bg="#0F5BD8",
            fg="white",
            activebackground="#0B4AB5",
            activeforeground="white",
            bd=0,
            padx=16,
            pady=9,
            font=("Segoe UI", 9, "bold"),
        )
        retry_button.pack(side="left")
        if retry is None:
            retry_button.configure(state="disabled")
        tk.Button(
            actions,
            text="Ver detalhes",
            command=show_details,
            bg="#E2E8F0",
            fg="#0F172A",
            activebackground="#CBD5E1",
            bd=0,
            padx=16,
            pady=9,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            actions,
            text="Fechar",
            command=dialog.destroy,
            bg="#F8FAFC",
            fg="#475569",
            bd=0,
            padx=14,
            pady=9,
            font=("Segoe UI", 9),
        ).pack(side="right")
        dialog.update_idletasks()
        dialog.grab_set()

    def import_source(self, _event=None) -> str:
        """Route PPTX directly to G2 while preserving Excel import."""

        path = filedialog.askopenfilename(
            parent=self,
            title="Importar campanha",
            filetypes=[("Excel / Canva PPTX", "*.xlsx *.xlsm *.pptx"), ("Todos", "*.*")],
        )
        if not path:
            return "break"
        source = Path(path)
        if source.suffix.lower() == ".pptx":
            self._launch_graphics2_source(source)
            return "break"
        try:
            result = self.workflow.import_source(path)
            messagebox.showinfo("Importação", result.message, parent=self)
            self.navigate("Encartes Studio")
            self._refresh_dirty()
        except Exception as exc:
            messagebox.showerror("Importação", f"Falha na importação.\n\n{exc}", parent=self)
        return "break"

    def _sync_graphics2_optional(self) -> None:
        """Importa alterações representáveis e resolve conflitos por campo."""

        result = sync_saved_session_to_project(self.project, self.data_dir)
        if result.ok:
            self._mark_changed()
            self.toast.show(result.message, "success", 6200)
            self.after(80, lambda: self.navigate("Encartes Studio"))
            return

        has_conflict = result.report is not None and bool(getattr(result.report, "conflict", False))
        if not has_conflict:
            self.toast.show(result.message, "danger", 7200)
            return

        analysis = analyze_saved_session_merge(self.project, self.data_dir)
        if not analysis.ok or analysis.report is None:
            self.toast.show(analysis.message, "danger", 7600)
            return
        if not analysis.report.conflict:
            merged = sync_saved_session_to_project(
                self.project,
                self.data_dir,
                merge_non_conflicting=True,
            )
            tone = "success" if merged.ok else "danger"
            if merged.ok:
                self._mark_changed()
                self.after(80, lambda: self.navigate("Encartes Studio"))
            self.toast.show(merged.message, tone, 7200)
            return

        decisions = ask_graphics2_merge_resolutions(self, analysis.report)
        if decisions is None:
            self.toast.show("Resolução de conflitos cancelada; nenhum campo foi sobrescrito.", "info", 5200)
            return

        resolved = resolve_saved_session_merge(
            self.project,
            self.data_dir,
            decisions,
            apply_non_conflicting=True,
        )
        if not resolved.ok:
            self.toast.show(resolved.message, "danger", 8200)
            return

        report = resolved.report
        applied = int(getattr(report, "applied", 0) or 0)
        explicitly_resolved = int(getattr(report, "resolved", 0) or 0)
        remaining = int(getattr(report, "unresolved_conflicts", 0) or 0)
        if applied or explicitly_resolved:
            self._mark_changed()
        tone = "warning" if remaining else "success"
        self.toast.show(resolved.message, tone, 8200)
        self.after(80, lambda: self.navigate("Encartes Studio"))

    def _start_background_staging(self, products, kind: PosterKind, campaign: str) -> None:
        self._staging_generation += 1
        generation = self._staging_generation
        total = len(products)
        if not total:
            return
        self._staging_active = True
        for product in products:
            product.metadata["render_state"] = "AGUARDANDO"
            product.metadata.pop("render_error", None)
        view = self._active_poster_view
        if hasattr(view, "set_render_progress"):
            view.set_render_progress(0, f"0/{total} · Renderização rápida preparando lote")
        if hasattr(view, "refresh_products"):
            view.refresh_products()
        self.toast.show(
            f"Renderização rápida · preparando {total} cartaz(es) com o engine SR compatível.",
            "info",
            3600,
        )
        self._ensure_staging_event_poll()

        def worker() -> None:
            def progress(event, index, event_total, product, valid, error) -> None:
                if event == "start":
                    self._staging_events.put(("item_start", generation, product.id, index, event_total))
                elif event == "done":
                    self._staging_events.put(
                        ("item_done", generation, product.id, index, event_total, valid, error)
                    )

            result = self._poster_staging.stage_many_turbo(
                products,
                kind,
                campaign,
                on_progress=progress,
            )
            self._staging_events.put(
                ("finished", generation, total, result.generated, result.reused, result.failed)
            )

        threading.Thread(target=worker, name="sr-poster-fast-staging", daemon=True).start()

    def _staging_finished(self, total: int, generated: int, reused: int, failed: int) -> None:
        if hasattr(self._active_poster_view, "set_render_progress"):
            ready = total - failed
            detail = f"{ready}/{total} prontos · Rápida"
            if reused:
                detail += f" · {reused} cache"
            if failed:
                detail += f" · {failed} erro(s)"
            self._active_poster_view.set_render_progress(100, detail)
        if failed:
            self.toast.show(
                f"Renderização concluída: {total - failed}/{total} prontos · {failed} precisam de revisão.",
                "warning",
                4800,
            )
        else:
            self.toast.show(
                f"Renderização rápida concluída · {generated} renderizado(s) + {reused} reaproveitado(s).",
                "success",
                4200,
            )


def run() -> None:
    advanced.base.PromotionPosterModule = cartazes_productivity.CartazesProductivityPromotionPosterModule
    advanced.base.WholesalePosterModule = cartazes_productivity.CartazesProductivityWholesalePosterModule
    app = SRStudioTurboPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()