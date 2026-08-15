from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from srstudio.core.models import StudioProject
from srstudio.validation.engine import ValidationEngine, ValidationIssue
from srstudio.validation.quality import QualityInspector


@dataclass(frozen=True, slots=True)
class PreflightReport:
    ready: bool
    issues: tuple[ValidationIssue, ...]
    quality: int
    errors: int
    warnings: int


class PreflightInspector:
    """Gate final antes de impressão/exportação da campanha."""

    def inspect(self, project: StudioProject, min_image_px: int = 500, min_quality: int = 70) -> PreflightReport:
        issues = list(ValidationEngine().validate_project(project))
        for product in project.products:
            if not product.image_path:
                continue
            path = Path(product.image_path)
            if not path.exists():
                continue
            try:
                with Image.open(path) as image:
                    smallest = min(image.width, image.height)
                    if smallest < min_image_px:
                        issues.append(
                            ValidationIssue(
                                "IMAGE_LOW_RESOLUTION",
                                "warning",
                                f"Imagem de {product.name} possui apenas {image.width}×{image.height}px.",
                                product.id,
                                field="image_path",
                            )
                        )
            except (OSError, ValueError):
                issues.append(
                    ValidationIssue(
                        "IMAGE_INVALID",
                        "warning",
                        f"Não foi possível ler a imagem de {product.name}.",
                        product.id,
                        field="image_path",
                    )
                )
        quality = QualityInspector().inspect(project).total
        if quality < min_quality:
            issues.append(
                ValidationIssue(
                    "QUALITY_BELOW_TARGET",
                    "warning",
                    f"Qualidade visual está em {quality}/100; meta mínima: {min_quality}/100.",
                )
            )
        summary = ValidationEngine.summary(issues)
        errors = summary.get("error", 0)
        warnings = summary.get("warning", 0)
        return PreflightReport(
            ready=errors == 0,
            issues=tuple(issues),
            quality=quality,
            errors=errors,
            warnings=warnings,
        )
