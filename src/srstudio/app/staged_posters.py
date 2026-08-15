from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

import srstudio.app.professional_posters as base
from srstudio.app.professional import _show_splash
from srstudio.posters import PosterKind
from srstudio.posters.staging import PosterStagingService


class _StagedPosterViewMixin:
    """Use print-quality staged artifacts for instant preview and final delivery."""

    def _ensure_staging(self) -> PosterStagingService:
        service = getattr(self, "_staging_service", None)
        if service is None:
            service = PosterStagingService()
            self._staging_service = service
        return service

    def _schedule_official_preview(self, product, decision) -> None:
        campaign = self._campaign_override()
        staged = self._ensure_staging().ready_artifact(product, self.kind, campaign)
        if staged is not None:
            self._show_staged_preview(staged, decision.short_label)
            return
        super()._schedule_official_preview(product, decision)

    def _show_staged_preview(self, path: Path, label: str) -> None:
        try:
            with Image.open(path) as source:
                image = source.convert("RGB")
                available_w = self.preview.winfo_width()
                available_h = self.preview.winfo_height()
                max_w = min(440, max(260, available_w - 24)) if available_w > 80 else 440
                max_h = min(550, max(300, available_h - 24)) if available_h > 80 else 520
                image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            self._preview_photo = ImageTk.PhotoImage(image, master=self.preview)
            self.preview.configure(image=self._preview_photo, text="")
            self.template_status.configure(text=f"AUTO · {label} · PRONTO")
        except Exception:
            pass

    def _generate_pdf(self) -> None:
        products = self._selected_products()
        if not products:
            messagebox.showinfo("Cartazes", "Nenhum produto selecionado para gerar.")
            return
        default = "Cartazes_Atacado.pdf" if self.is_wholesale else "Cartazes_Promocao.pdf"
        path = filedialog.asksaveasfilename(
            initialfile=default,
            defaultextension=".pdf",
            filetypes=[("PDF para impressão", "*.pdf")],
        )
        if not path:
            return
        self.status_label.configure(text="Validando cartazes temporários e montando o PDF final...")
        self.update_idletasks()
        try:
            output = self._ensure_staging().promote_pdf(
                products,
                self.kind,
                path,
                self._campaign_override(),
            )
        except Exception as exc:
            self.status_label.configure(text="Falha na validação dos cartazes temporários.")
            messagebox.showerror("Gerar cartazes", str(exc))
            return
        self._last_pdf = Path(output)
        self.status_label.configure(text=f"PDF final pronto · {len(products)} cartaz(es) validados.")
        self._notify("PDF montado a partir dos cartazes já pré-renderizados.", "success")

    def _generate_pngs(self) -> None:
        products = self._selected_products()
        if not products:
            return
        directory = filedialog.askdirectory(title="Pasta para os cartazes PNG")
        if not directory:
            return
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        campaign = self._campaign_override()
        copied = 0
        try:
            for index, product in enumerate(products, start=1):
                source = self._ensure_staging().ready_artifact(product, self.kind, campaign)
                if source is None:
                    artifact = self._ensure_staging().stage_one(product, self.kind, campaign)
                    if not artifact.valid:
                        raise RuntimeError(f"{product.name}: {artifact.error}")
                    source = artifact.path
                name = re.sub(r"[^A-Za-z0-9À-ÿ _.-]+", "", product.name).strip()[:70] or f"cartaz_{index}"
                shutil.copy2(source, target / f"{index:03d}_{name}.png")
                copied += 1
        except Exception as exc:
            messagebox.showerror("Gerar PNGs", str(exc))
            return
        self.status_label.configure(text=f"{copied} PNG(s) final(is) liberados sem nova renderização.")
        self._notify(f"{copied} cartaz(es) PNG prontos.", "success")


class StagedPromotionPosterModule(_StagedPosterViewMixin, base.PromotionPosterModule):
    pass


class StagedWholesalePosterModule(_StagedPosterViewMixin, base.WholesalePosterModule):
    pass


class SRStudioStagedPosters(base.SRStudioPosterProfessional):
    """Poster shell that starts final-quality temporary rendering immediately after import."""

    def __init__(self) -> None:
        self._staging_generation = 0
        self._poster_staging = PosterStagingService()
        super().__init__()

    def _import_poster_source(self, kind: PosterKind) -> int:
        count = super()._import_poster_source(kind)
        if count <= 0:
            return count
        products = self._poster_queue_snapshot(kind)
        campaign = "" if kind == PosterKind.PROMOTION else "Atacado"
        self._start_background_staging(products, kind, campaign)
        return count

    def _poster_queue_snapshot(self, kind: PosterKind):
        queues = self.project.settings.get("poster_queues", {})
        ids = list(queues.get(kind.value, [])) if isinstance(queues, dict) else []
        lookup = {product.id: product for product in self.project.products}
        return [lookup[product_id] for product_id in ids if product_id in lookup]

    def _start_background_staging(self, products, kind: PosterKind, campaign: str) -> None:
        self._staging_generation += 1
        generation = self._staging_generation
        total = len(products)
        if not total:
            return
        self.toast.show(
            f"Preparando {total} cartaz(es) em qualidade final no segundo plano...",
            "info",
            4200,
        )

        def worker() -> None:
            generated = reused = failed = 0
            for index, product in enumerate(products, start=1):
                artifact_path = self._poster_staging.ready_artifact(product, kind, campaign)
                was_ready = artifact_path is not None
                artifact = self._poster_staging.stage_one(product, kind, campaign)
                if artifact.valid:
                    if was_ready:
                        reused += 1
                    else:
                        generated += 1
                else:
                    failed += 1
                if generation == self._staging_generation:
                    self.after(
                        0,
                        lambda done=index, total=total: self._staging_progress(done, total),
                    )
            if generation == self._staging_generation:
                self.after(
                    0,
                    lambda: self._staging_finished(total, generated, reused, failed),
                )

        threading.Thread(target=worker, name="sr-poster-staging", daemon=True).start()

    def _staging_progress(self, done: int, total: int) -> None:
        self.toast.show(f"Cartazes pré-renderizados: {done}/{total} prontos.", "info", 1400)

    def _staging_finished(self, total: int, generated: int, reused: int, failed: int) -> None:
        if failed:
            self.toast.show(
                f"Pré-geração concluída: {total - failed}/{total} prontos · {failed} precisam de revisão.",
                "warning",
                5200,
            )
        else:
            self.toast.show(
                f"{total} cartaz(es) prontos em cache · {generated} renderizado(s), {reused} reaproveitado(s).",
                "success",
                5200,
            )


def run() -> None:
    # The existing shell looks these classes up in its module globals. Replacing only
    # the concrete poster views preserves navigation/design while adding staging.
    base.PromotionPosterModule = StagedPromotionPosterModule
    base.WholesalePosterModule = StagedWholesalePosterModule
    app = SRStudioStagedPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
