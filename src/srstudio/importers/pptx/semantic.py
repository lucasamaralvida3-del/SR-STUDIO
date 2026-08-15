from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .reader import PptxElement, PptxSlide


PRICE_RE = re.compile(r"(?:R\$\s*)?(\d{1,4})(?:[,.](\d{2}))")


@dataclass(slots=True)
class SemanticCard:
    image: PptxElement | None = None
    name: PptxElement | None = None
    price: PptxElement | None = None
    unit: PptxElement | None = None
    confidence: float = 0.0
    extras: list[PptxElement] = field(default_factory=list)


class SemanticMapper:
    """Heurísticas espaciais para converter elementos PPTX em cards de produto."""

    def map_slide(self, slide: PptxSlide) -> list[SemanticCard]:
        texts = [e for e in slide.elements if e.kind == "text" and e.text]
        images = [e for e in slide.elements if e.kind == "image"]
        prices = [e for e in texts if self._looks_like_price(e.text)]
        names = [e for e in texts if e not in prices and self._looks_like_product_name(e.text)]
        cards: list[SemanticCard] = []
        used_names: set[int] = set()
        used_images: set[int] = set()

        for price in prices:
            name = self._nearest(price, names, used_names, vertical_bias=-0.8)
            image = self._nearest(price, images, used_images, vertical_bias=-0.3)
            if name is not None:
                used_names.add(id(name))
            if image is not None:
                used_images.add(id(image))
            confidence = 0.45
            if name is not None:
                confidence += 0.30
            if image is not None:
                confidence += 0.20
            if self._price_value(price.text) is not None:
                confidence += 0.05
            cards.append(SemanticCard(image=image, name=name, price=price, confidence=min(confidence, 1.0)))
        return cards

    @staticmethod
    def _looks_like_price(text: str) -> bool:
        return PRICE_RE.search(text.replace(" ", "")) is not None

    @staticmethod
    def _price_value(text: str) -> Decimal | None:
        match = PRICE_RE.search(text.replace(" ", ""))
        if not match:
            return None
        try:
            return Decimal(f"{match.group(1)}.{match.group(2)}")
        except InvalidOperation:
            return None

    @staticmethod
    def _looks_like_product_name(text: str) -> bool:
        cleaned = text.strip()
        if len(cleaned) < 3 or len(cleaned) > 120:
            return False
        if cleaned.count(" ") < 1:
            return False
        upper = cleaned.upper()
        blocked = ("OFERTA", "VALIDADE", "SUPER", "CLUBE", "APP", "IMAGENS MERAMENTE")
        return not any(token in upper for token in blocked)

    def _nearest(self, origin: PptxElement, candidates: list[PptxElement], used: set[int], vertical_bias: float) -> PptxElement | None:
        ox = origin.x + origin.width / 2
        oy = origin.y + origin.height / 2
        best = None
        best_score = float("inf")
        for candidate in candidates:
            if id(candidate) in used:
                continue
            cx = candidate.x + candidate.width / 2
            cy = candidate.y + candidate.height / 2
            dx = abs(cx - ox)
            dy = abs(cy - oy)
            directional_bonus = vertical_bias * max(0.0, oy - cy)
            score = dx + dy + directional_bonus
            if score < best_score:
                best, best_score = candidate, score
        return best
