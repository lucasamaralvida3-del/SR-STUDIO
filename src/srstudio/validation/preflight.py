from __future__ import annotations

from dataclasses import dataclass

from srstudio.core.models import StudioProject
from srstudio.images.quality import ImageQualityAnalyzer
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

    def __init__(self) -> None:
        self.images = ImageQualityAnalyzer()

    def inspect(self, project: StudioProject, min_image_px: int = 500, min_quality: int = 70) -> PreflightReport:
        issues = list(ValidationEngine().validate_project(project))
        image_paths: list[str] = []
        products_by_path: dict[str, list] = {}
        for product in project.products:
            if not product.image_path:
                continue
            image_paths.append(product.image_path)
            products_by_path.setdefault(product.image_path, []).append(product)
            report = self.images.inspect(product.image_path)
            if not report.exists:
                continue
            if "Imagem inválida ou corrompida" in report.issues:
                issues.append(
                    ValidationIssue(
                        "IMAGE_INVALID",
                        "warning",
                        f"Não foi possível ler a imagem de {product.name}.",
                        product.id,
                        field="image_path",
                    )
                )
                continue
            smallest = min(report.width, report.height)
            if smallest < min_image_px:
                issues.append(
                    ValidationIssue(
                        "IMAGE_LOW_RESOLUTION",
                        "warning",
                        f"Imagem de {product.name} possui apenas {report.width}×{report.height}px.",
                        product.id,
                        field="image_path",
                    )
                )
            if report.score < 50:
                issues.append(
                    ValidationIssue(
                        "IMAGE_QUALITY_LOW",
                        "warning",
                        f"Qualidade técnica da imagem de {product.name}: {report.score}/100.",
                        product.id,
                        field="image_path",
                    )
                )

        duplicates = self.images.duplicates(image_paths)
        for paths in duplicates.values():
            names: list[str] = []
            for path in paths:
                names.extend(product.name for product in products_by_path.get(path, []))
            unique_names = list(dict.fromkeys(names))
            if len(unique_names) > 1:
                issues.append(
                    ValidationIssue(
                        "IMAGE_DUPLICATE_REVIEW",
                        "warning",
                        "A mesma imagem está associada a produtos diferentes: " + ", ".join(unique_names[:5]),
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
