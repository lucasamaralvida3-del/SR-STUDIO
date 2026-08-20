from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from math import sqrt
from pathlib import Path
from statistics import pstdev
from typing import Any

from PIL import Image, ImageFilter, ImageStat


@dataclass(frozen=True, slots=True)
class ImageQuality:
    path: str
    exists: bool
    width: int = 0
    height: int = 0
    megapixels: float = 0.0
    has_alpha: bool = False
    format: str = ""
    score: int = 0
    checksum: str = ""
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductImageQuality:
    """Fine-grained 0..1 score used only after product identity is established."""

    score: float
    resolution_score: float
    transparency_score: float
    sharpness_score: float
    border_cleanliness_score: float
    transparent_ratio: float
    edge_stddev: float
    border_stddev: float
    penalties: tuple[str, ...] = ()

    def metadata(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["quality_score"] = payload.pop("score")
        return payload


class ImageQualityAnalyzer:
    """Avaliação técnica determinística para biblioteca, preflight e ranking."""

    def inspect(self, path: str | Path) -> ImageQuality:
        """Compatibility preflight API retained for existing callers."""
        source = Path(path)
        if not source.exists() or not source.is_file():
            return ImageQuality(str(source), False, issues=("Arquivo não encontrado",))
        data = source.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        try:
            with Image.open(source) as image:
                width, height = image.size
                megapixels = round((width * height) / 1_000_000, 2)
                has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
                fmt = image.format or source.suffix.lstrip(".").upper()
        except (OSError, ValueError):
            return ImageQuality(str(source), True, checksum=checksum, issues=("Imagem inválida ou corrompida",))

        issues: list[str] = []
        smallest = min(width, height)
        if smallest < 300:
            issues.append("Resolução muito baixa")
        elif smallest < 600:
            issues.append("Resolução abaixo do recomendado")
        if width <= 0 or height <= 0:
            issues.append("Dimensões inválidas")
        score = 100
        if smallest < 300:
            score -= 55
        elif smallest < 600:
            score -= 25
        if megapixels < 0.25:
            score -= 20
        return ImageQuality(str(source), True, width, height, megapixels, has_alpha, fmt, max(0, score), checksum, tuple(issues))

    def product_quality(self, path: str | Path, *, metadata: dict | None = None) -> ProductImageQuality:
        """Analyze a product asset once; callers persist the returned metadata.

        OCR/price/multi-product detection remains review-first and optional. When
        those probabilities are already known they are penalties here; this method
        never tries to infer product identity from visual quality.
        """
        source = Path(path)
        with Image.open(source) as image:
            width, height = image.size
            megapixels = (width * height) / 1_000_000.0
            resolution_score = min(1.0, sqrt(max(megapixels, 0.0) / 1.5))

            rgba = image.convert("RGBA")
            rgba.thumbnail((192, 192))
            alpha = rgba.getchannel("A")
            alpha_hist = alpha.histogram()
            total = max(1, sum(alpha_hist))
            transparent_ratio = sum(alpha_hist[:245]) / total
            if 0.02 <= transparent_ratio <= 0.92:
                transparency_score = 1.0
            elif transparent_ratio < 0.02:
                transparency_score = 0.55
            else:
                transparency_score = 0.35

            gray = rgba.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stddev = float(ImageStat.Stat(edges).stddev[0])
            sharpness_score = min(1.0, edge_stddev / 42.0)

            rgb = rgba.convert("RGB")
            w, h = rgb.size
            border_values: list[int] = []
            if w and h:
                px = rgb.load()
                for x in range(w):
                    border_values.extend(px[x, 0])
                    if h > 1:
                        border_values.extend(px[x, h - 1])
                for y in range(1, max(1, h - 1)):
                    border_values.extend(px[0, y])
                    if w > 1:
                        border_values.extend(px[w - 1, y])
            border_stddev = float(pstdev(border_values)) if len(border_values) > 1 else 255.0
            border_cleanliness_score = max(0.0, min(1.0, 1.0 - border_stddev / 95.0))

        score = (
            0.36 * resolution_score
            + 0.18 * transparency_score
            + 0.26 * sharpness_score
            + 0.20 * border_cleanliness_score
        )

        known = dict(metadata or {})
        penalties: list[str] = []
        penalty_specs = (
            ("contains_text_probability", 0.28, "text-overlay"),
            ("contains_price_probability", 0.34, "price-overlay"),
            ("multi_product_probability", 0.34, "multiple-products"),
            ("partial_product_probability", 0.30, "partial-product"),
            ("watermark_probability", 0.20, "watermark"),
            ("background_clutter_probability", 0.15, "background-clutter"),
        )
        for key, weight, label in penalty_specs:
            try:
                probability = max(0.0, min(1.0, float(known.get(key, 0.0) or 0.0)))
            except (TypeError, ValueError):
                probability = 0.0
            if probability >= 0.35:
                penalties.append(label)
            score *= 1.0 - weight * probability

        return ProductImageQuality(
            score=round(max(0.0, min(1.0, score)), 6),
            resolution_score=round(resolution_score, 6),
            transparency_score=round(transparency_score, 6),
            sharpness_score=round(sharpness_score, 6),
            border_cleanliness_score=round(border_cleanliness_score, 6),
            transparent_ratio=round(transparent_ratio, 6),
            edge_stddev=round(edge_stddev, 6),
            border_stddev=round(border_stddev, 6),
            penalties=tuple(penalties),
        )

    def duplicates(self, paths: list[str | Path]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for path in paths:
            result = self.inspect(path)
            if result.checksum:
                groups.setdefault(result.checksum, []).append(result.path)
        return {checksum: items for checksum, items in groups.items() if len(items) > 1}


def asset_quality_score(asset: Any) -> float:
    """Read ranking quality from metadata without opening pixels interactively."""
    metadata = dict(getattr(asset, "metadata", {}) or {})
    try:
        stored = float(metadata.get("quality_score"))
    except (TypeError, ValueError):
        stored = -1.0
    if 0.0 <= stored <= 1.0:
        return stored

    megapixels = float(getattr(asset, "megapixels", 0.0) or 0.0)
    fallback = min(1.0, sqrt(max(megapixels, 0.0) / 1.5))
    if str(getattr(asset, "mode", "")).upper() in {"RGBA", "LA"}:
        fallback = min(1.0, fallback + 0.08)
    return round(fallback, 6)
