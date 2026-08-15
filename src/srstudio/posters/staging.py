from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PIL import Image

from srstudio.core.models import Product
from srstudio.posters.core import PosterKind
from srstudio.posters.preview import LegacyPosterPreviewService


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

    def signature(self, product: Product, kind: PosterKind, campaign: str = "") -> str:
        payload = {
            "kind": kind.value,
            "campaign": campaign,
            "product": product.to_dict(),
            "promotion_type": product.metadata.get("promotion_type"),
            "profile": f"print-{self.PRINT_WIDTH}x{self.PRINT_HEIGHT}-v1",
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:40]

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
            rendered = self.renderer.render(
                product,
                kind,
                campaign,
                width=self.PRINT_WIDTH,
                height=self.PRINT_HEIGHT,
                cache_namespace="staging-print-v1",
            )
            if rendered != destination:
                shutil.copy2(rendered, destination)
            valid, width, height, error = self._validate_image(destination)
            return StagedPoster(product.id, signature, destination, width, height, valid, error)
        except Exception as exc:
            return StagedPoster(product.id, signature, destination, 0, 0, False, str(exc))

    def stage_many(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        campaign: str = "",
    ) -> StagingBatchResult:
        result = StagingBatchResult()
        for product in products:
            destination = self.artifact_path(product, kind, campaign)
            was_ready = self._validate_image(destination)[0]
            artifact = self.stage_one(product, kind, campaign)
            result.artifacts.append(artifact)
            if artifact.valid:
                if was_ready:
                    result.reused += 1
                else:
                    result.generated += 1
            else:
                result.failed += 1
        return result

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
