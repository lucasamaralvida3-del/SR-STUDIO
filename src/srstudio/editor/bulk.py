from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from srstudio.core.models import Product, ProductCard, StudioProject


@dataclass(frozen=True, slots=True)
class BulkResult:
    affected: int
    description: str


class BulkOperations:
    """Operações em lote sem duplicar regras na interface."""

    def __init__(self, project: StudioProject) -> None:
        self.project = project

    def cards(self, predicate: Callable[[ProductCard], bool] | None = None) -> list[ProductCard]:
        all_cards = [card for page in self.project.pages for card in page.cards]
        return [card for card in all_cards if predicate(card)] if predicate else all_cards

    def products(self, predicate: Callable[[Product], bool] | None = None) -> list[Product]:
        return [item for item in self.project.products if predicate(item)] if predicate else list(self.project.products)

    def set_card_style(self, style_id: str, cards: list[ProductCard] | None = None) -> BulkResult:
        targets = cards or self.cards()
        for card in targets:
            card.style_id = style_id
        return BulkResult(len(targets), f"Estilo '{style_id}' aplicado em {len(targets)} card(s).")

    def set_price_scale(self, scale: float, cards: list[ProductCard] | None = None) -> BulkResult:
        value = max(0.25, min(float(scale), 4.0))
        targets = cards or self.cards()
        for card in targets:
            card.overrides["price_scale"] = value
        return BulkResult(len(targets), f"Escala de preço {value:.2f} aplicada em {len(targets)} card(s).")

    def set_highlight_by_product_ids(self, product_ids: set[str]) -> BulkResult:
        affected = 0
        for card in self.cards():
            highlighted = card.product_id in product_ids
            affected += int(card.highlighted != highlighted)
            card.highlighted = highlighted
        return BulkResult(affected, f"Destaques atualizados em {affected} card(s).")

    def normalize_units(self) -> BulkResult:
        changed = 0
        aliases = {"UND": "UN", "UNID": "UN", "KILO": "KG", "QUILO": "KG", "KGS": "KG"}
        for product in self.project.products:
            current = str(product.unit or "").strip().upper()
            normalized = aliases.get(current, current or "UN")
            if normalized != product.unit:
                product.unit = normalized
                changed += 1
        return BulkResult(changed, f"{changed} unidade(s) normalizada(s).")

    def hide_empty_limits(self) -> BulkResult:
        affected = 0
        products = {item.id: item for item in self.project.products}
        for card in self.cards():
            product = products.get(card.product_id)
            if product is not None and not str(product.cpf_limit or "").strip():
                if card.overrides.get("show_limit", True):
                    card.overrides["show_limit"] = False
                    affected += 1
        return BulkResult(affected, f"Limite vazio ocultado em {affected} card(s).")
