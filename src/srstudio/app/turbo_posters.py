from __future__ import annotations

import threading

import srstudio.app.advanced_posters as advanced
import srstudio.app.responsive_posters as responsive
from srstudio.app.professional import _show_splash
from srstudio.posters import PosterKind


class SRStudioTurboPosters(responsive.SRStudioResponsivePosters):
    """Responsive poster shell with persistent-session PowerPoint batch staging."""

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
            view.set_render_progress(0, f"0/{total} · Turbo Renderer preparando lote")
        if hasattr(view, "refresh_products"):
            view.refresh_products()
        self.toast.show(
            f"Turbo Renderer · preparando {total} cartaz(es) em uma única sessão do PowerPoint.",
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

        threading.Thread(target=worker, name="sr-poster-turbo-staging", daemon=True).start()

    def _staging_finished(self, total: int, generated: int, reused: int, failed: int) -> None:
        if hasattr(self._active_poster_view, "set_render_progress"):
            ready = total - failed
            detail = f"{ready}/{total} prontos · Turbo"
            if reused:
                detail += f" · {reused} cache"
            if failed:
                detail += f" · {failed} erro(s)"
            self._active_poster_view.set_render_progress(100, detail)
        if failed:
            self.toast.show(
                f"Turbo concluído: {total - failed}/{total} prontos · {failed} precisam de revisão.",
                "warning",
                4800,
            )
        else:
            self.toast.show(
                f"Turbo concluído · {generated} renderizado(s) + {reused} reaproveitado(s) do cache.",
                "success",
                4200,
            )


def run() -> None:
    advanced.base.PromotionPosterModule = responsive.ResponsivePromotionPosterModule
    advanced.base.WholesalePosterModule = responsive.ResponsiveWholesalePosterModule
    app = SRStudioTurboPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
