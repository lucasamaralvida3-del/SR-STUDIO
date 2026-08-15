from __future__ import annotations

import hashlib
import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image

from srstudio.core.models import Product
from srstudio.posters.auto_model import PosterAutoModelResolver
from srstudio.posters.core import PosterKind
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
    """Pre-render official posters once, then reuse them for preview/final delivery."""

    PRINT_WIDTH = 1772
    PRINT_HEIGHT = 2480

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.home() / ".srstudio5" / "cache" / "poster-staging"
        self.root.mkdir(parents=True, exist_ok=True)
        self.renderer = LegacyPosterPreviewService(self.root / "render-cache")
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
            "profile": f"print-{self.PRINT_WIDTH}x{self.PRINT_HEIGHT}-v4-turbo-safe",
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

    def stage_one(self, product: Product, kind: PosterKind, campaign: str = "") -> StagedPoster:
        signature = self.signature(product, kind, campaign)
        destination = self.artifact_path(product, kind, campaign)
        valid, width, height, _ = self._validate_image(destination)
        if valid:
            return StagedPoster(product.id, signature, destination, width, height, True)

        try:
            with _POWERPOINT_STAGE_LOCK:
                rendered = self.renderer.render(
                    product,
                    kind,
                    campaign,
                    width=self.PRINT_WIDTH,
                    height=self.PRINT_HEIGHT,
                    cache_namespace="staging-print-v4-turbo-safe-fallback",
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
        """Render uncached posters in one PowerPoint session with per-item safe fallback.

        A Turbo item error is never considered final. Every item whose Turbo output is
        missing/invalid is retried through the proven single-item renderer. Therefore
        an Office-specific Turbo incompatibility cannot turn a valid batch into 0 posters.
        """
        selected = list(products)
        total = len(selected)
        result = StagingBatchResult()
        artifacts: dict[str, StagedPoster] = {}
        missing: list[tuple[int, Product, Path, str]] = []

        for index, product in enumerate(selected, start=1):
            signature = self.signature(product, kind, campaign)
            destination = self.artifact_path(product, kind, campaign)
            valid, width, height, _ = self._validate_image(destination)
            if valid:
                artifact = StagedPoster(product.id, signature, destination, width, height, True)
                artifacts[product.id] = artifact
                result.reused += 1
                if on_progress is not None:
                    on_progress("start", index, total, product, True, "cache")
                    on_progress("done", index, total, product, True, "cache")
            else:
                missing.append((index, product, destination, signature))

        if missing:
            outputs = {product.id: destination for _, product, destination, _ in missing}
            by_batch_index = {batch_index: item for batch_index, item in enumerate(missing, start=1)}
            turbo_success: set[str] = set()
            turbo_errors: dict[str, str] = {}

            def turbo_progress(event: str, batch_index: int, detail: str) -> None:
                item = by_batch_index.get(batch_index)
                if item is None:
                    return
                original_index, product, destination, signature = item
                if event == "start":
                    if on_progress is not None:
                        on_progress("start", original_index, total, product, False, "turbo")
                    return
                if event == "ok":
                    valid, width, height, error = self._validate_image(destination)
                    if valid:
                        artifacts[product.id] = StagedPoster(
                            product.id, signature, destination, width, height, True
                        )
                        if product.id not in turbo_success:
                            turbo_success.add(product.id)
                            result.generated += 1
                            if on_progress is not None:
                                on_progress("done", original_index, total, product, True, "turbo")
                    else:
                        turbo_errors[product.id] = error or "Turbo gerou arquivo inválido"
                elif event == "err":
                    turbo_errors[product.id] = detail or "Falha no Turbo Renderer"

            batch_error = ""
            try:
                with _POWERPOINT_STAGE_LOCK:
                    self.renderer.render_many_to(
                        [product for _, product, _, _ in missing],
                        kind,
                        outputs,
                        campaign,
                        width=self.PRINT_WIDTH,
                        height=self.PRINT_HEIGHT,
                        on_progress=turbo_progress,
                    )
            except Exception as exc:
                batch_error = str(exc)

            for original_index, product, destination, signature in missing:
                if product.id in turbo_success:
                    continue

                valid, width, height, validation_error = self._validate_image(destination)
                if valid:
                    artifacts[product.id] = StagedPoster(
                        product.id, signature, destination, width, height, True
                    )
                    result.generated += 1
                    turbo_success.add(product.id)
                    if on_progress is not None:
                        on_progress("done", original_index, total, product, True, "turbo")
                    continue

                if on_progress is not None:
                    on_progress("start", original_index, total, product, False, "fallback")
                fallback = self.stage_one(product, kind, campaign)
                if fallback.valid:
                    artifacts[product.id] = fallback
                    result.generated += 1
                    if on_progress is not None:
                        on_progress("done", original_index, total, product, True, "fallback")
                    continue

                parts = [
                    turbo_errors.get(product.id, ""),
                    batch_error,
                    validation_error,
                    fallback.error,
                ]
                detail = " | ".join(dict.fromkeys(part.strip() for part in parts if part and part.strip()))
                final = StagedPoster(
                    product.id,
                    signature,
                    destination,
                    fallback.width,
                    fallback.height,
                    False,
                    detail or "Turbo e fallback não conseguiram gerar o cartaz.",
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

    def promote_pdf(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        destination: str | Path,
        campaign: str = "",
    ) -> Path:
        paths: list[Path] = []
        for product in products:
            path = self.ready_artifact(product, kind, campaign)
            if path is None:
                staged = self.stage_one(product, kind, campaign)
                if not staged.valid:
                    raise RuntimeError(f"Cartaz de {product.name} não passou na validação: {staged.error}")
                path = staged.path
            paths.append(path)
        if not paths:
            raise RuntimeError("Nenhum cartaz válido para gerar o PDF.")

        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
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
