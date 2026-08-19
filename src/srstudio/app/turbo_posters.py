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
    """Official SR Studio shell with Studio de Encartes G2 as primary editor."""

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
        # Encartes Studio is intercepted before the inherited navigation can
        # instantiate the legacy Tk canvas.  The old implementation remains in
        # the parent class and is available through an explicit fallback button.
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
        """Primary human entrypoint for the full Studio de Encartes G2 flow."""

        root = tk.Frame(self.content, bg="#F4F7FB")
        root.pack(fill="both", expand=True, padx=28, pady=24)

        hero = tk.Frame(
            root,
            bg="white",
            highlightbackground="#D9E2EF",
            highlightthickness=1,
        )
        hero.pack(fill="x")
        title = tk.Frame(hero, bg="white")
        title.pack(fill="x", padx=26, pady=(24, 8))
        tk.Label(
            title,
            text="STUDIO DE ENCARTES G2",
            bg="white",
            fg="#0F5BD8",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title,
            text="Novo editor oficial de encartes do SR Studio",
            bg="white",
            fg="#111827",
            font=("Segoe UI", 19, "bold"),
        ).pack(anchor="w", pady=(3, 0))
        tk.Label(
            title,
            text=(
                "Importe o PPTX exportado do Canva pelo pipeline real do SR Studio e abra o documento "
                "diretamente no editor Graphics Engine 2."
            ),
            bg="white",
            fg="#64748B",
            font=("Segoe UI", 10),
            justify="left",
            wraplength=940,
        ).pack(anchor="w", pady=(8, 4))

        actions = tk.Frame(hero, bg="white")
        actions.pack(fill="x", padx=26, pady=(12, 26))
        self._g2_action_button(
            actions,
            "IMPORTAR CANVA / PPTX",
            "Abrir um .pptx e converter pelo import bridge real",
            self._choose_graphics2_pptx,
            primary=True,
        ).pack(side="left", fill="x", expand=True, padx=(0, 7))
        self._g2_action_button(
            actions,
            "ABRIR PROJETO G2",
            "Reabrir um .srscene/.zip salvo pelo editor",
            self._choose_graphics2_project,
        ).pack(side="left", fill="x", expand=True, padx=7)
        self._g2_action_button(
            actions,
            "PROJETO ATUAL",
            "Levar o projeto atual do SR Studio ao G2",
            self._launch_current_project_in_graphics2,
        ).pack(side="left", fill="x", expand=True, padx=(7, 0))

        flow = tk.Frame(root, bg="#EAF2FF")
        flow.pack(fill="x", pady=(16, 0))
        tk.Label(
            flow,
            text="FLUXO ATIVO",
            bg="#EAF2FF",
            fg="#0F5BD8",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", padx=18, pady=(14, 2))
        tk.Label(
            flow,
            text="PPTX / Canva  →  Import Bridge / Office Layout  →  SR Scene 2  →  Editor G2",
            bg="#EAF2FF",
            fg="#1E3A5F",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=18, pady=(0, 14))

        compatibility = tk.Frame(root, bg="#F4F7FB")
        compatibility.pack(fill="x", pady=(18, 0))
        tk.Label(
            compatibility,
            text="Compatibilidade",
            bg="#F4F7FB",
            fg="#64748B",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        tk.Button(
            compatibility,
            text="Abrir editor legado (fallback)",
            command=self._open_legacy_encartes_fallback,
            bg="#E2E8F0",
            fg="#334155",
            activebackground="#CBD5E1",
            activeforeground="#0F172A",
            relief="flat",
            bd=0,
            padx=12,
            pady=7,
            font=("Segoe UI", 8),
            cursor="hand2",
        ).pack(side="left", padx=(12, 0))

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
        self._show_graphics2_launch_result(result)

    def _launch_current_project_in_graphics2(self) -> None:
        result = launch_studio_project(self.project, self.data_dir)
        self._show_graphics2_launch_result(result)

    def _show_graphics2_launch_result(self, result) -> None:
        if result.launched:
            self.toast.show(result.message, "success", 5600)
            return
        tone = "warning" if result.ok else "danger"
        self.toast.show(result.message, tone, 7600)
        if not result.ok:
            messagebox.showerror("Studio de Encartes G2", result.message, parent=self)

    def _open_legacy_encartes_fallback(self) -> None:
        # Intentionally bypass this class' route override.  This keeps the old
        # editor available while G2 is being certified, but never as the default.
        super().navigate("Encartes Studio")
        self.toast.show("Editor legado aberto em modo de compatibilidade.", "warning", 4800)

    def import_source(self, _event=None) -> str:
        """Route PPTX directly to G2 while preserving Excel legacy import."""

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
            # A análise detalhada pode concluir que só existem mudanças
            # independentes. Nesse caso o merge seguro resolve sem diálogo.
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
    # Encartes Studio now routes to Graphics Engine 2.  Promoções/Atacado keep
    # their current productivity modules until their own migration is certified.
    advanced.base.PromotionPosterModule = cartazes_productivity.CartazesProductivityPromotionPosterModule
    advanced.base.WholesalePosterModule = cartazes_productivity.CartazesProductivityWholesalePosterModule
    app = SRStudioTurboPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
