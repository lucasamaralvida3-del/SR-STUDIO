from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from srstudio.core.models import Product, StudioProject


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    product_id: str = ""
    page_id: str = ""
    field: str = ""


class ValidationEngine:
    def validate_product(self, product: Product) -> list[ValidationIssue]:
        out: list[ValidationIssue] = []
        if not product.name.strip():
            out.append(ValidationIssue("PRODUCT_NAME_MISSING", "error", "Produto sem nome.", product.id, field="name"))
        if product.price is None:
            out.append(ValidationIssue("PRICE_MISSING", "error", f"{product.name or 'Produto'} está sem preço.", product.id, field="price"))
        elif product.price <= Decimal("0"):
            out.append(ValidationIssue("PRICE_INVALID", "error", f"{product.name} possui preço inválido.", product.id, field="price"))
        if product.unit not in {"UN", "KG", "CX", "PCT", "FD", "BDJ", "LT", "L"}:
            out.append(ValidationIssue("UNIT_REVIEW", "warning", f"Unidade '{product.unit}' precisa de revisão em {product.name}.", product.id, field="unit"))
        if not product.image_path:
            out.append(ValidationIssue("IMAGE_MISSING", "warning", f"{product.name} está sem imagem.", product.id, field="image_path"))
        elif not Path(product.image_path).exists():
            out.append(ValidationIssue("IMAGE_NOT_FOUND", "warning", f"A imagem de {product.name} não foi encontrada.", product.id, field="image_path"))
        if product.recognition_confidence < 0.70:
            out.append(ValidationIssue("LOW_CONFIDENCE", "warning", f"Reconhecimento de {product.name} precisa de confirmação.", product.id))
        return out

    def validate_project(self, project: StudioProject) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        seen: dict[str, str] = {}
        for product in project.products:
            issues.extend(self.validate_product(product))
            identity = (product.ean or product.code or product.name).strip().upper()
            if identity and identity in seen:
                issues.append(ValidationIssue("PRODUCT_DUPLICATE", "warning", f"Produto duplicado: {product.name}.", product.id))
            elif identity:
                seen[identity] = product.id
        if not project.pages:
            issues.append(ValidationIssue("PAGE_MISSING", "error", "O projeto não possui páginas."))
        for page in project.pages:
            for card in page.cards:
                if project.product_by_id(card.product_id) is None:
                    issues.append(ValidationIssue("CARD_PRODUCT_BROKEN", "error", "Card aponta para produto inexistente.", page_id=page.id))
                if card.width <= 0 or card.height <= 0:
                    issues.append(ValidationIssue("CARD_SIZE_INVALID", "error", "Card possui tamanho inválido.", page_id=page.id))
                if card.x < 0 or card.y < 0 or card.x + card.width > page.width or card.y + card.height > page.height:
                    issues.append(ValidationIssue("CARD_OUTSIDE_PAGE", "warning", "Card ultrapassa a área da página.", page_id=page.id))
        return issues

    @staticmethod
    def summary(issues: Iterable[ValidationIssue]) -> dict[str, int]:
        result = {"error": 0, "warning": 0, "info": 0}
        for issue in issues:
            result[issue.severity] = result.get(issue.severity, 0) + 1
        return result
