from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from srstudio.core.models import StudioProject
from srstudio.validation.engine import ValidationEngine
from srstudio.validation.preflight import PreflightInspector
from srstudio.validation.quality import QualityInspector


@dataclass(frozen=True, slots=True)
class AuditSummary:
    products: int
    pages: int
    cards: int
    missing_images: int
    validation_errors: int
    validation_warnings: int
    quality: int
    ready_to_export: bool
    orphan_products: int


class ProjectAudit:
    """Visão única da saúde de um projeto para UI, suporte e diagnóstico."""

    def inspect(self, project: StudioProject) -> AuditSummary:
        issues = ValidationEngine().validate_project(project)
        counts = ValidationEngine.summary(issues)
        quality = QualityInspector().inspect(project).total
        preflight = PreflightInspector().inspect(project)
        used = {card.product_id for page in project.pages for card in page.cards}
        orphan = sum(product.id not in used for product in project.products)
        missing_images = sum(not product.image_path or not Path(product.image_path).exists() for product in project.products)
        return AuditSummary(
            products=len(project.products),
            pages=len(project.pages),
            cards=sum(len(page.cards) for page in project.pages),
            missing_images=missing_images,
            validation_errors=counts.get("error", 0),
            validation_warnings=counts.get("warning", 0),
            quality=quality,
            ready_to_export=preflight.ready,
            orphan_products=orphan,
        )
