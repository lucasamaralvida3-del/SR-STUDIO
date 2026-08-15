from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


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


class ImageQualityAnalyzer:
    """Avaliação técnica determinística para biblioteca e preflight."""

    def inspect(self, path: str | Path) -> ImageQuality:
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

    def duplicates(self, paths: list[str | Path]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for path in paths:
            result = self.inspect(path)
            if result.checksum:
                groups.setdefault(result.checksum, []).append(result.path)
        return {checksum: items for checksum, items in groups.items() if len(items) > 1}
