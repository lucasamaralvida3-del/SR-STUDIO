from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image
from pypdf import PdfReader, PdfWriter

from srstudio.core.models import Product
from srstudio.posters.auto_model import PosterAutoModelResolver
from srstudio.posters.core import PosterKind
from srstudio.posters.legacy_batch import LegacyBatchRenderer
from srstudio.posters.preview import LegacyPosterPreviewService


_POWERPOINT_STAGE_LOCK = threading.Lock()
StageProgress = Callable[[str, int, int, Product, bool, str], None]


@dataclass(frozen=True, slots=True)
class StagedPoster:
    product_id: str
    signature: str
    path: Path
    width: int
    height: int
    valid: bool
    error: str = ""


@dataclass(slots=True)
class StagingBatchResult:
    artifacts: list[StagedPoster] = field(default_factory=list)
    generated: int = 0
    reused: int = 0
    failed: int = 0


class PosterStagingService:
    """Prepare official posters once and reuse PDF/PNG artifacts thereafter.

    The fast path deliberately leaves the historical PowerPoint engines untouched:
    they generate vector PDFs exactly as in the previous SR Studio versions. PDFium
    converts those PDFs to preview PNGs without any extra PowerPoint automation.
    """

    PRINT_WIDTH = 1772
    PRINT_HEIGHT = 2480

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.home() / ".srstudio5" / "cache" / "poster-staging"
        self.root.mkdir(parents=True, exist_ok=True)
        self.renderer = LegacyPosterPreviewService(self.root / "render-cache")
        self.batch_renderer = LegacyBatchRenderer()
        self.model_resolver = PosterAutoModelResolver()
        self._model_hashes: dict[str, str] = {}

    def signature(self, product: Product, kind: PosterKind, campaign: str = "") -> str:
        decision = self.model_resolver.decide(product, kind)
        effective_campaign = campaign or product.campaign
        payload = {
            "kind": kind.value,
            "campaign": effective_campaign,
            "code": product.code,
            "name": product.name,
            "price": None if product.price is None else str(product.price),
            "app_price": None if product.app_price is None else str(product.app_price),
            "retail_price": None if product.retail_price is None else str(product.retail_price),
            "wholesale_price": None if product.wholesale_price is None else str(product.wholesale_price),
            "unit": product.unit,
            "quantity": product.quantity,
            "limit": product.cpf_limit,
            "validity": product.validity,
            "promotion_type": product.metadata.get("promotion_type"),
            "model": decision.filename,
            "model_revision": self._model_revision(decision.path),
            "profile": f"print-{self.PRINT_WIDTH}x{self.PRINT_HEIGHT}-v6-untouched-engine-pdfium",
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:40]

    def _model_revision(self, path: Path) -> str:
        key = str(path.resolve())
        cached = self._model_hashes.get(key)
        if cached is not None:
            return cached
        if not path.is_file():
            revision = "missing"
        else:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            revision = digest.hexdigest()[:20]
        self._model_hashes[key] = revision
        return revision

    def artifact_path(self, product: Product, kind: PosterKind, campaign: str = "") -> Path:
        signature = self.signature(product, kind, campaign)
        folder = self.root / kind.value
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{signature}.png"

    def pdf_artifact_path(self, product: Product, kind: PosterKind, campaign: str = "") -> Path:
        return self.artifact_path(product, kind, campaign).with_suffix(".pdf")

    def stage_one(self, product: Product, kind: PosterKind, campaign: str = "") -> StagedPoster:
        signature = self.signature(product, kind, campaign)
        destination = self.artifact_path(product, kind, campaign)
        valid, width, height, _ = self._validate_image(destination)
        if valid:
            return StagedPoster(product.id, signature, destination, width, height, True)

        # If the vector PDF is already cached, rebuilding the preview never touches Office.
        cached_pdf = self.ready_pdf_artifact(product, kind, campaign)
        if cached_pdf is not None:
            artifact = self._poster_from_pdf(product, kind, campaign, cached_pdf)
            if artifact.valid:
                return artifact

        # Proven compatibility fallback: the exact single-item preview renderer from 7.8.
        try:
            with _POWERPOINT_STAGE_LOCK:
                rendered = self.renderer.render(
                    product,
                    kind,
                    campaign,
                    width=self.PRINT_WIDTH,
                    height=self.PRINT_HEIGHT,
                    cache_namespace="staging-print-v6-normal-fallback",
                )
            if rendered != destination:
                shutil.copy2(rendered, destination)
            valid, width, height, error = self._validate_image(destination)
            return StagedPoster(product.id, signature, destination, width, height, valid, error)
        except Exception as exc:
            return StagedPoster(product.id, signature, destination, 0, 0, False, str(exc))

    def stage_many_turbo(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        campaign: str = "",
        *,
        on_progress: StageProgress | None = None,
    ) -> StagingBatchResult:
        """Fast path: untouched old batch engine -> vector PDF -> PDFium preview.

        The method name remains for UI/backward compatibility only. No experimental
        Turbo PowerPoint automation is used here.
        """
        selected = list(products)
        total = len(selected)
        result = StagingBatchResult()
        artifacts: dict[str, StagedPoster] = {}
        missing: list[tuple[int, Product, str]] = []

        # Reuse PNG immediately; if only PDF exists, recreate PNG locally with PDFium.
        for index, product in enumerate(selected, start=1):
            signature = self.signature(product, kind, campaign)
            destination = self.artifact_path(product, kind, campaign)
            valid, width, height, _ = self._validate_image(destination)
            if valid:
                artifacts[product.id] = StagedPoster(product.id, signature, destination, width, height, True)
                result.reused += 1
                if on_progress is not None:
                    on_progress("start", index, total, product, True, "cache")
                    on_progress("done", index, total, product, True, "cache")
                continue

            pdf = self.ready_pdf_artifact(product, kind, campaign)
            if pdf is not None:
                if on_progress is not None:
                    on_progress("start", index, total, product, True, "pdf-cache")
                artifact = self._poster_from_pdf(product, kind, campaign, pdf)
                if artifact.valid:
                    artifacts[product.id] = artifact
                    result.reused += 1
                    if on_progress is not None:
                        on_progress("done", index, total, product, True, "PDF cache · prévia local")
                    continue
            missing.append((index, product, signature))

        if missing:
            by_batch_index = {batch_index: item for batch_index, item in enumerate(missing, start=1)}
            completed_fast: set[str] = set()
            fast_errors: dict[str, str] = {}
            started: set[str] = set()

            with tempfile.TemporaryDirectory(prefix="srstudio-proven-batch-") as temp_name:
                output_dir = Path(temp_name) / "pdfs"
                output_dir.mkdir(parents=True, exist_ok=True)

                def engine_progress(event: str, batch_index: int, detail: str) -> None:
                    item = by_batch_index.get(batch_index)
                    if item is None:
                        return
                    original_index, product, _signature = item
                    if event == "stage":
                        if product.id not in started:
                            started.add(product.id)
                            if on_progress is not None:
                                on_progress(
                                    "start",
                                    original_index,
                                    total,
                                    product,
                                    False,
                                    "engine histórico em lote",
                                )
                        return
                    if event == "err":
                        fast_errors[product.id] = detail or "falha no engine histórico em lote"
                        return
                    if event != "ok":
                        return

                    # The old engine has completed the official vector PDF. Copy it to
                    # the persistent signature cache, then rasterize locally with PDFium.
                    source_pdf = Path(detail)
                    if not source_pdf.is_file():
                        fast_errors[product.id] = "engine informou PDF, mas o arquivo não existe"
                        return
                    pdf_destination = self.pdf_artifact_path(product, kind, campaign)
                    try:
                        shutil.copy2(source_pdf, pdf_destination)
                        artifact = self._poster_from_pdf(product, kind, campaign, pdf_destination)
                    except Exception as exc:
                        fast_errors[product.id] = str(exc)
                        return
                    if artifact.valid:
                        artifacts[product.id] = artifact
                        completed_fast.add(product.id)
                        result.generated += 1
                        if on_progress is not None:
                            on_progress(
                                "done",
                                original_index,
                                total,
                                product,
                                True,
                                "PDF oficial + prévia PDFium",
                            )
                    else:
                        fast_errors[product.id] = artifact.error

                batch_error = ""
                try:
                    with _POWERPOINT_STAGE_LOCK:
                        batch = self.batch_renderer.render_pdfs(
                            [product for _, product, _ in missing],
                            kind,
                            output_dir,
                            campaign,
                            on_progress=engine_progress,
                        )
                    batch_error = batch.batch_error

                    # Recover PDFs discovered after process exit that were not observed
                    # through stdout (for example Office buffering output).
                    for batch_index, source_pdf in batch.files.items():
                        item = by_batch_index.get(batch_index)
                        if item is None:
                            continue
                        original_index, product, _signature = item
                        if product.id in completed_fast:
                            continue
                        try:
                            pdf_destination = self.pdf_artifact_path(product, kind, campaign)
                            shutil.copy2(source_pdf, pdf_destination)
                            artifact = self._poster_from_pdf(product, kind, campaign, pdf_destination)
                        except Exception as exc:
                            fast_errors[product.id] = str(exc)
                            continue
                        if artifact.valid:
                            artifacts[product.id] = artifact
                            completed_fast.add(product.id)
                            result.generated += 1
                            if on_progress is not None:
                                on_progress(
                                    "done",
                                    original_index,
                                    total,
                                    product,
                                    True,
                                    "PDF oficial + prévia PDFium",
                                )
                        else:
                            fast_errors[product.id] = artifact.error
                    for batch_index, detail in batch.errors.items():
                        item = by_batch_index.get(batch_index)
                        if item is not None:
                            fast_errors[item[1].id] = detail
                except Exception as exc:
                    batch_error = str(exc)

            # Compatibility fallback only for products the untouched batch engine did not finish.
            for original_index, product, signature in missing:
                if product.id in completed_fast:
                    continue
                if on_progress is not None:
                    on_progress("start", original_index, total, product, False, "modo compatível")
                fallback = self.stage_one(product, kind, campaign)
                if fallback.valid:
                    artifacts[product.id] = fallback
                    result.generated += 1
                    if on_progress is not None:
                        on_progress("done", original_index, total, product, True, "modo compatível")
                    continue

                parts = [fast_errors.get(product.id, ""), batch_error, fallback.error]
                detail = " | ".join(dict.fromkeys(part.strip() for part in parts if part and part.strip()))
                final = StagedPoster(
                    product.id,
                    signature,
                    self.artifact_path(product, kind, campaign),
                    fallback.width,
                    fallback.height,
                    False,
                    detail or "Engine histórico em lote e modo compatível não conseguiram gerar o cartaz.",
                )
                artifacts[product.id] = final
                result.failed += 1
                if on_progress is not None:
                    on_progress("done", original_index, total, product, False, final.error)

        result.artifacts = [artifacts[product.id] for product in selected if product.id in artifacts]
        return result

    def stage_many(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        campaign: str = "",
    ) -> StagingBatchResult:
        return self.stage_many_turbo(products, kind, campaign)

    def ready_artifact(self, product: Product, kind: PosterKind, campaign: str = "") -> Path | None:
        path = self.artifact_path(product, kind, campaign)
        return path if self._validate_image(path)[0] else None

    def ready_pdf_artifact(self, product: Product, kind: PosterKind, campaign: str = "") -> Path | None:
        path = self.pdf_artifact_path(product, kind, campaign)
        return path if self._validate_pdf(path) else None

    def promote_pdf(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        destination: str | Path,
        campaign: str = "",
    ) -> Path:
        selected = list(products)
        if not selected:
            raise RuntimeError("Nenhum cartaz válido para gerar o PDF.")

        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)

        # Preferred path: merge the official vector PDFs already produced by the old engine.
        cached_pdfs: list[Path] = []
        for product in selected:
            pdf = self.ready_pdf_artifact(product, kind, campaign)
            if pdf is None:
                cached_pdfs = []
                break
            cached_pdfs.append(pdf)
        if cached_pdfs:
            writer = PdfWriter()
            for pdf in cached_pdfs:
                reader = PdfReader(str(pdf))
                for page in reader.pages:
                    writer.add_page(page)
            with output.open("wb") as handle:
                writer.write(handle)
            return output

        # Compatibility path for items produced only by the normal preview renderer.
        paths: list[Path] = []
        for product in selected:
            path = self.ready_artifact(product, kind, campaign)
            if path is None:
                staged = self.stage_one(product, kind, campaign)
                if not staged.valid:
                    raise RuntimeError(f"Cartaz de {product.name} não passou na validação: {staged.error}")
                path = staged.path
            paths.append(path)

        pages: list[Image.Image] = []
        try:
            for path in paths:
                with Image.open(path) as source:
                    page = source.convert("RGB")
                    if page.size != (self.PRINT_WIDTH, self.PRINT_HEIGHT):
                        raise RuntimeError(f"Cartaz temporário fora do padrão de impressão: {path.name}")
                    pages.append(page.copy())
            first, *rest = pages
            first.save(output, "PDF", save_all=True, append_images=rest, resolution=300.0)
        finally:
            for page in pages:
                page.close()
        return output

    def _poster_from_pdf(
        self,
        product: Product,
        kind: PosterKind,
        campaign: str,
        pdf_path: Path,
    ) -> StagedPoster:
        signature = self.signature(product, kind, campaign)
        destination = self.artifact_path(product, kind, campaign)
        if not self._validate_pdf(pdf_path):
            return StagedPoster(product.id, signature, destination, 0, 0, False, "PDF temporário inválido")
        try:
            self.batch_renderer.rasterize_pdf(
                pdf_path,
                destination,
                width=self.PRINT_WIDTH,
                height=self.PRINT_HEIGHT,
            )
        except Exception as exc:
            return StagedPoster(product.id, signature, destination, 0, 0, False, str(exc))
        valid, width, height, error = self._validate_image(destination)
        return StagedPoster(product.id, signature, destination, width, height, valid, error)

    @classmethod
    def _validate_image(cls, path: Path) -> tuple[bool, int, int, str]:
        if not path.is_file() or path.stat().st_size < 4096:
            return False, 0, 0, "arquivo temporário ausente ou incompleto"
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
            if (width, height) != (cls.PRINT_WIDTH, cls.PRINT_HEIGHT):
                return False, width, height, "resolução temporária diferente do padrão 300 dpi"
            return True, width, height, ""
        except Exception as exc:
            return False, 0, 0, str(exc)

    @staticmethod
    def _validate_pdf(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size < 256:
            return False
        try:
            return len(PdfReader(str(path)).pages) >= 1
        except Exception:
            return False
