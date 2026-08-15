from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from srstudio.core.models import Product, ProductCard
from srstudio.pricing.engine import PriceEngine


@dataclass(frozen=True, slots=True)
class CardRegion:
    name: str
    x: float
    y: float
    width: float
    height: float
    z: int = 0


@dataclass(slots=True)
class ProductCardStyle:
    id: str
    name: str
    image_region: CardRegion
    name_region: CardRegion
    price_region: CardRegion
    unit_region: CardRegion | None = None
    limit_region: CardRegion | None = None
    background: str = "#FFFFFF"
    border: str = "#E2E8F0"
    text_color: str = "#162033"
    price_color: str = "#0B5DCE"
    image_fit: str = "contain"
    metadata: dict[str, Any] = field(default_factory=dict)


DEFAULT_STYLE = ProductCardStyle(
    id="product-card-default",
    name="Produto padrão",
    image_region=CardRegion("image", 0.05, 0.05, 0.90, 0.54),
    name_region=CardRegion("name", 0.06, 0.59, 0.88, 0.15),
    price_region=CardRegion("price", 0.06, 0.74, 0.68, 0.22),
    unit_region=CardRegion("unit", 0.74, 0.79, 0.20, 0.10),
    limit_region=CardRegion("limit", 0.06, 0.93, 0.88, 0.05),
)

HERO_STYLE = ProductCardStyle(
    id="product-card-hero",
    name="Produto destaque",
    image_region=CardRegion("image", 0.03, 0.06, 0.52, 0.86),
    name_region=CardRegion("name", 0.56, 0.10, 0.40, 0.22),
    price_region=CardRegion("price", 0.56, 0.38, 0.36, 0.38),
    unit_region=CardRegion("unit", 0.84, 0.62, 0.12, 0.10),
    limit_region=CardRegion("limit", 0.56, 0.82, 0.40, 0.08),
)


@dataclass(frozen=True, slots=True)
class CardViewModel:
    product_id: str
    name: str
    image_path: str
    currency: str
    integer: str
    decimal: str
    unit: str
    limit: str
    style: ProductCardStyle


class ProductCardRegistry:
    def __init__(self) -> None:
        self._styles: dict[str, ProductCardStyle] = {
            DEFAULT_STYLE.id: DEFAULT_STYLE,
            HERO_STYLE.id: HERO_STYLE,
        }
        self._price_engine = PriceEngine()

    def register(self, style: ProductCardStyle) -> None:
        self._styles[style.id] = style

    def get(self, style_id: str) -> ProductCardStyle:
        return self._styles.get(style_id, DEFAULT_STYLE)

    def all(self) -> tuple[ProductCardStyle, ...]:
        return tuple(self._styles.values())

    def view_model(self, card: ProductCard, product: Product) -> CardViewModel:
        imported = card.overrides.get("imported_style")
        if isinstance(imported, dict) and imported:
            style = self._imported_style(card, imported)
        else:
            style_id = "product-card-hero" if card.highlighted and card.style_id == DEFAULT_STYLE.id else card.style_id
            style = self.get(style_id)
        parts = self._price_engine.split(product.price, product.unit)
        name = str(card.overrides.get("name") or product.name)
        image_path = str(card.overrides.get("image_path") or product.image_path)
        unit = str(card.overrides.get("unit") or product.unit)
        limit = str(card.overrides.get("cpf_limit") or product.cpf_limit)
        return CardViewModel(
            product_id=product.id,
            name=name,
            image_path=image_path,
            currency=parts.currency,
            integer=parts.integer,
            decimal=parts.cents,
            unit=unit,
            limit=limit,
            style=style,
        )

    def _imported_style(self, card: ProductCard, spec: dict[str, Any]) -> ProductCardStyle:
        image_region = self._region("image", spec.get("image_region"), DEFAULT_STYLE.image_region)
        name_region = self._region("name", spec.get("name_region"), DEFAULT_STYLE.name_region)
        price_region = self._region("price", spec.get("price_region"), DEFAULT_STYLE.price_region)
        unit_region = self._region("unit", spec.get("unit_region"), DEFAULT_STYLE.unit_region, optional=True)
        name_style = dict(spec.get("name_style") or {})
        price_style = dict(spec.get("price_style") or {})
        text_color = self._hex_color(name_style.get("fill"), DEFAULT_STYLE.text_color)
        price_color = self._hex_color(price_style.get("fill"), DEFAULT_STYLE.price_color)
        return ProductCardStyle(
            id=f"canva-{card.id}",
            name="Canva importado",
            image_region=image_region,
            name_region=name_region,
            price_region=price_region,
            unit_region=unit_region,
            limit_region=None,
            background="#FFFFFF",
            border="",
            text_color=text_color,
            price_color=price_color,
            image_fit=str(spec.get("image_fit") or "contain"),
            metadata={
                "imported_from_canva": True,
                "transparent_background": True,
                "name_style": name_style,
                "price_style": price_style,
                "cents_style": dict(spec.get("cents_style") or {}),
                "currency_style": dict(spec.get("currency_style") or {}),
            },
        )

    @staticmethod
    def _region(
        name: str,
        value: Any,
        fallback: CardRegion | None,
        *,
        optional: bool = False,
    ) -> CardRegion | None:
        if not isinstance(value, dict) or not value:
            return None if optional else fallback
        try:
            x = max(-0.25, min(1.25, float(value.get("x", 0.0))))
            y = max(-0.25, min(1.25, float(value.get("y", 0.0))))
            width = max(0.01, min(1.5, float(value.get("width", 0.0))))
            height = max(0.01, min(1.5, float(value.get("height", 0.0))))
            return CardRegion(name, x, y, width, height)
        except (TypeError, ValueError):
            return None if optional else fallback

    @staticmethod
    def _hex_color(value: Any, fallback: str) -> str:
        text = str(value or "")
        return text if text.startswith("#") and len(text) in {4, 7, 9} else fallback
