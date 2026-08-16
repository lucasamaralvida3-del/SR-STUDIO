from __future__ import annotations

import threading

import srstudio.app.advanced_posters as advanced
import srstudio.app.cartazes_table_visual as cartazes_visual
import srstudio.app.responsive_posters as responsive
from srstudio.app.cloud_image_bank_view import CloudImageBankView
from srstudio.app.layout_corpus_view import LayoutCorpusView
from srstudio.app.professional import _show_splash
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
    # Cartazes Pro receives the high-legibility table layer only in the dedicated
    # Promoções/Atacado modules. Encartes Studio remains on its own graphics pipeline.
    advanced.base.PromotionPosterModule = cartazes_visual.CartazesVisualPromotionPosterModule
    advanced.base.WholesalePosterModule = cartazes_visual.CartazesVisualWholesalePosterModule
    app = SRStudioTurboPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
