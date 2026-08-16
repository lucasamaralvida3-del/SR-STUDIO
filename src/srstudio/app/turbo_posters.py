from __future__ import annotations

import threading
import tkinter as tk

import srstudio.app.advanced_posters as advanced
import srstudio.app.cartazes_pro as cartazes
import srstudio.app.responsive_posters as responsive
from srstudio.app.cloud_image_bank_view import CloudImageBankView
from srstudio.app.graphics2_merge_dialog import ask_graphics2_merge_resolutions
from srstudio.app.layout_corpus_view import LayoutCorpusView
from srstudio.app.professional import _show_splash
from srstudio.graphics2.saved_merge import analyze_saved_session_merge, resolve_saved_session_merge
from srstudio.graphics2.studio_bridge import (
    bridge_flags,
    launch_studio_project_if_enabled,
    sync_saved_session_to_project,
)
from srstudio.images.cloud_sync import ImageBankCloudSync
from srstudio.posters import PosterKind


class SRStudioTurboPosters(responsive.SRStudioResponsivePosters):
    """Responsive poster shell plus the professional Encartes Studio experience."""

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
        if name == "Encartes Studio":
            self._attach_graphics2_launcher()
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

    def _attach_graphics2_launcher(self) -> None:
        """Mostra controles G2 somente quando a feature flag foi ligada manualmente."""

        engine_enabled, gpu_enabled = bridge_flags(self.data_dir)
        if not engine_enabled:
            return
        children = list(self.content.winfo_children())
        if not children:
            return
        editor = children[-1]
        label = "ENGINE 2 · GPU" if gpu_enabled else "ENGINE 2 · TESTE"
        button = tk.Button(
            editor,
            text=label,
            command=self._launch_graphics2_optional,
            bg="#0F5BD8",
            fg="white",
            activebackground="#0B46AA",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        sync_button = tk.Button(
            editor,
            text="APLICAR G2",
            command=self._sync_graphics2_optional,
            bg="#E2E8F0",
            fg="#0F172A",
            activebackground="#CBD5E1",
            activeforeground="#0F172A",
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        # Overlays intencionais e isolados: não alteram o layout Tk antigo e só
        # existem no modo experimental. Quando a flag está off, nem são criados.
        button.place(relx=1.0, x=-150, y=13, anchor="ne")
        sync_button.place(relx=1.0, x=-276, y=13, anchor="ne")

    def _launch_graphics2_optional(self) -> None:
        result = launch_studio_project_if_enabled(self.project, self.data_dir)
        if result.launched:
            self.toast.show(result.message, "success", 5200)
            return
        tone = "warning" if result.ok else "danger"
        self.toast.show(result.message, tone, 6200)

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
    # Cartazes Pro é aplicado somente aos módulos dedicados Promoções/Atacado.
    # Encartes Studio continua no pipeline gráfico/importador do Engine 2 sem
    # monkey-patch do seu canvas ou de seus Smart Slots.
    advanced.base.PromotionPosterModule = cartazes.CartazesProPromotionPosterModule
    advanced.base.WholesalePosterModule = cartazes.CartazesProWholesalePosterModule
    app = SRStudioTurboPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
