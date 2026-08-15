from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .reader import PptxElement, PptxSlide


PRICE_RE = re.compile(r"(?:R\$\s*)?(\d{1,4})(?:[,.](\d{2}))")
INTEGER_RE = re.compile(r"^\d{1,4}$")
CENTS_RE = re.compile(r"^[,.]\d{2}$")
UNIT_RE = re.compile(r"^(?:/\s*)?(UN|KG|L|LT|ML|G|GR|CX|PCT|BDJ|LATA|GARRAFA)$", re.IGNORECASE)
CURRENCY_RE = re.compile(r"^R\$$", re.IGNORECASE)


@dataclass(slots=True)
class PriceCluster:
    value: Decimal | None = None
    currency: PptxElement | None = None
    integer: PptxElement | None = None
    cents: PptxElement | None = None
    unit: PptxElement | None = None
    complete: PptxElement | None = None
    elements: list[PptxElement] = field(default_factory=list)

    @property
    def anchor(self) -> PptxElement | None:
        return self.integer or self.complete or self.currency or self.cents


@dataclass(slots=True)
class SemanticCard:
    image: PptxElement | None = None
    name: PptxElement | None = None
    price: PptxElement | None = None
    unit: PptxElement | None = None
    price_value: Decimal | None = None
    price_cluster: PriceCluster | None = None
    secondary_price: PriceCluster | None = None
    confidence: float = 0.0
    extras: list[PptxElement] = field(default_factory=list)
    bounds: tuple[int, int, int, int] | None = None
    style_spec: dict = field(default_factory=dict)


class SemanticMapper:
    """Canva-aware spatial heuristics for reconstructing editable product cards."""

    BLOCKED = (
        "OFERTA",
        "OFERTAS",
        "VALIDADE",
        "VÁLIDO",
        "SUPER",
        "CLUBE",
        "APP",
        "IMAGENS MERAMENTE",
        "ENQUANTO DURAREM",
        "RODRIGUES",
        "ECONOMIA",
        "TERÇA VERDE",
        "QUARTA CAFÉ",
        "QUINTA FILÉ",
        "FIM DE SEMANA",
        "HORTIFRUTI",
        "LIMPEZA",
    )

    def map_slide(self, slide: PptxSlide) -> list[SemanticCard]:
        texts = [element for element in slide.elements if element.kind == "text" and element.text.strip()]
        images = [
            element
            for element in slide.elements
            if element.kind == "image" and element.media_path and self._image_candidate(element, slide)
        ]
        clusters = self._price_clusters(texts, slide)
        price_element_ids = {id(element) for cluster in clusters for element in cluster.elements}
        names = [
            element
            for element in texts
            if id(element) not in price_element_ids and self._looks_like_product_name(element.text)
        ]

        cards: list[SemanticCard] = []
        used_names: set[int] = set()
        used_images: set[int] = set()

        for cluster in clusters:
            anchor = cluster.anchor
            if anchor is None or cluster.value is None:
                continue
            name = self._nearest_semantic(anchor, names, used_names, slide, role="name")
            image = self._nearest_semantic(anchor, images, used_images, slide, role="image")

            # A second price in the same visual card normally has no new product name/image.
            existing = self._near_existing_card(cluster, cards, slide)
            if existing is not None and name is None and image is None and existing.secondary_price is None:
                existing.secondary_price = cluster
                existing.confidence = min(1.0, existing.confidence + 0.06)
                continue

            if name is not None:
                used_names.add(id(name))
            if image is not None:
                used_images.add(id(image))

            semantic_elements = list(cluster.elements)
            if name is not None:
                semantic_elements.append(name)
            if image is not None:
                semantic_elements.append(image)
            bounds = self._bounds(semantic_elements)
            confidence = self._confidence(cluster, name, image)
            card = SemanticCard(
                image=image,
                name=name,
                price=cluster.anchor,
                unit=cluster.unit,
                price_value=cluster.value,
                price_cluster=cluster,
                confidence=confidence,
                bounds=bounds,
            )
            card.style_spec = self._style_spec(card)
            cards.append(card)

        return cards

    def _price_clusters(self, texts: list[PptxElement], slide: PptxSlide) -> list[PriceCluster]:
        clusters: list[PriceCluster] = []
        used: set[int] = set()

        # Preserve the rare case where Canva exported a full price in one text box.
        for element in texts:
            value = self._price_value(element.text)
            if value is None:
                continue
            cluster = PriceCluster(value=value, complete=element, elements=[element])
            unit = self._near_unit(element, texts, used, slide)
            if unit is not None:
                cluster.unit = unit
                cluster.elements.append(unit)
                used.add(id(unit))
            clusters.append(cluster)
            used.add(id(element))

        currencies = [element for element in texts if CURRENCY_RE.fullmatch(self._clean(element.text))]
        integers = [element for element in texts if INTEGER_RE.fullmatch(self._clean(element.text))]
        cents = [element for element in texts if CENTS_RE.fullmatch(self._clean(element.text))]

        for currency in currencies:
            if id(currency) in used:
                continue
            integer = self._best_price_part(currency, integers, used, slide, "integer")
            if integer is None:
                continue
            local_used = set(used)
            local_used.add(id(integer))
            cent = self._best_price_part(integer, cents, local_used, slide, "cents")
            if cent is None:
                continue
            try:
                value = Decimal(f"{self._clean(integer.text)}.{self._clean(cent.text)[1:]}")
            except InvalidOperation:
                continue
            cluster = PriceCluster(
                value=value,
                currency=currency,
                integer=integer,
                cents=cent,
                elements=[currency, integer, cent],
            )
            local_used.update((id(currency), id(cent)))
            unit = self._near_unit(cent, texts, local_used, slide)
            if unit is not None:
                cluster.unit = unit
                cluster.elements.append(unit)
                local_used.add(id(unit))
            used.update(local_used)
            clusters.append(cluster)

        # Some Canva templates omit the R$ object and keep only integer + cents.
        for integer in integers:
            if id(integer) in used:
                continue
            cent = self._best_price_part(integer, cents, used | {id(integer)}, slide, "cents")
            if cent is None:
                continue
            try:
                value = Decimal(f"{self._clean(integer.text)}.{self._clean(cent.text)[1:]}")
            except InvalidOperation:
                continue
            cluster = PriceCluster(value=value, integer=integer, cents=cent, elements=[integer, cent])
            local_used = used | {id(integer), id(cent)}
            unit = self._near_unit(cent, texts, local_used, slide)
            if unit is not None:
                cluster.unit = unit
                cluster.elements.append(unit)
                local_used.add(id(unit))
            used.update(local_used)
            clusters.append(cluster)

        return sorted(clusters, key=lambda item: (item.anchor.y if item.anchor else 0, item.anchor.x if item.anchor else 0))

    def _best_price_part(
        self,
        origin: PptxElement,
        candidates: list[PptxElement],
        used: set[int],
        slide: PptxSlide,
        role: str,
    ) -> PptxElement | None:
        ox, oy = self._center(origin)
        best: tuple[float, PptxElement] | None = None
        for candidate in candidates:
            if id(candidate) in used or candidate is origin:
                continue
            cx, cy = self._center(candidate)
            dx = (cx - ox) / max(slide.width, 1)
            dy = (cy - oy) / max(slide.height, 1)
            if role == "integer":
                if dx < -0.02 or dx > 0.14 or abs(dy) > 0.055:
                    continue
                score = abs(dy) * 4.0 + abs(dx - 0.035)
            else:
                if dx < -0.015 or dx > 0.13 or abs(dy) > 0.07:
                    continue
                score = abs(dy) * 3.2 + abs(dx - 0.035)
            if best is None or score < best[0]:
                best = (score, candidate)
        return best[1] if best is not None else None

    def _near_unit(
        self,
        origin: PptxElement,
        texts: list[PptxElement],
        used: set[int],
        slide: PptxSlide,
    ) -> PptxElement | None:
        candidates = [
            element
            for element in texts
            if id(element) not in used and UNIT_RE.fullmatch(self._clean(element.text))
        ]
        ox, oy = self._center(origin)
        best: tuple[float, PptxElement] | None = None
        for candidate in candidates:
            cx, cy = self._center(candidate)
            dx = abs(cx - ox) / max(slide.width, 1)
            dy = abs(cy - oy) / max(slide.height, 1)
            if dx > 0.15 or dy > 0.085:
                continue
            score = dx + dy * 1.5
            if best is None or score < best[0]:
                best = (score, candidate)
        return best[1] if best is not None else None

    def _nearest_semantic(
        self,
        origin: PptxElement,
        candidates: list[PptxElement],
        used: set[int],
        slide: PptxSlide,
        role: str,
    ) -> PptxElement | None:
        ox, oy = self._center(origin)
        best: tuple[float, PptxElement] | None = None
        for candidate in candidates:
            if id(candidate) in used:
                continue
            cx, cy = self._center(candidate)
            dx = abs(cx - ox) / max(slide.width, 1)
            dy_signed = (cy - oy) / max(slide.height, 1)
            dy = abs(dy_signed)
            if role == "name":
                if dx > 0.22 or dy > 0.24:
                    continue
                # Product names are commonly just above the price.
                directional = 0.0 if dy_signed <= 0.04 else dy_signed * 0.8
                score = dx * 1.25 + dy + directional
            else:
                if dx > 0.25 or dy > 0.30:
                    continue
                area_ratio = (candidate.width * candidate.height) / max(slide.width * slide.height, 1)
                score = dx + dy * 0.85 + max(0.0, area_ratio - 0.10) * 0.8
            if best is None or score < best[0]:
                best = (score, candidate)
        return best[1] if best is not None else None

    def _near_existing_card(
        self,
        cluster: PriceCluster,
        cards: list[SemanticCard],
        slide: PptxSlide,
    ) -> SemanticCard | None:
        anchor = cluster.anchor
        if anchor is None:
            return None
        ax, ay = self._center(anchor)
        best: tuple[float, SemanticCard] | None = None
        for card in cards:
            other = card.price_cluster.anchor if card.price_cluster else card.price
            if other is None:
                continue
            bx, by = self._center(other)
            dx = abs(ax - bx) / max(slide.width, 1)
            dy = abs(ay - by) / max(slide.height, 1)
            if dx <= 0.19 and dy <= 0.12:
                score = dx + dy
                if best is None or score < best[0]:
                    best = (score, card)
        return best[1] if best is not None else None

    @staticmethod
    def _confidence(cluster: PriceCluster, name: PptxElement | None, image: PptxElement | None) -> float:
        confidence = 0.34
        if cluster.currency is not None or cluster.complete is not None:
            confidence += 0.10
        if cluster.cents is not None or cluster.complete is not None:
            confidence += 0.08
        if cluster.unit is not None:
            confidence += 0.05
        if name is not None:
            confidence += 0.23
        if image is not None:
            confidence += 0.20
        return min(1.0, confidence)

    def _style_spec(self, card: SemanticCard) -> dict:
        if card.bounds is None:
            return {}
        left, top, right, bottom = card.bounds
        width = max(1, right - left)
        height = max(1, bottom - top)

        def region(element: PptxElement | None) -> dict:
            if element is None:
                return {}
            return {
                "x": (element.x - left) / width,
                "y": (element.y - top) / height,
                "width": element.width / width,
                "height": element.height / height,
            }

        cluster = card.price_cluster
        price_elements = cluster.elements if cluster is not None else ([card.price] if card.price else [])
        price_bounds = self._bounds(price_elements) if price_elements else None
        if price_bounds is not None:
            px1, py1, px2, py2 = price_bounds
            price_region = {
                "x": (px1 - left) / width,
                "y": (py1 - top) / height,
                "width": (px2 - px1) / width,
                "height": (py2 - py1) / height,
            }
        else:
            price_region = {}
        return {
            "image_region": region(card.image),
            "name_region": region(card.name),
            "price_region": price_region,
            "unit_region": region(card.unit),
            "name_style": self._element_style(card.name),
            "price_style": self._element_style(cluster.integer if cluster else card.price),
            "cents_style": self._element_style(cluster.cents if cluster else None),
            "currency_style": self._element_style(cluster.currency if cluster else None),
            "image_fit": "cover" if card.image and card.image.metadata.get("crop") else "contain",
        }

    @staticmethod
    def _element_style(element: PptxElement | None) -> dict:
        if element is None:
            return {}
        return {
            key: element.metadata.get(key)
            for key in ("font_name", "font_size_pt", "bold", "italic", "fill", "align", "rotation")
            if element.metadata.get(key) not in (None, "", 0, 0.0, False)
        }

    @staticmethod
    def _bounds(elements: list[PptxElement]) -> tuple[int, int, int, int] | None:
        valid = [element for element in elements if element.width > 0 and element.height > 0]
        if not valid:
            return None
        return (
            min(element.x for element in valid),
            min(element.y for element in valid),
            max(element.x + element.width for element in valid),
            max(element.y + element.height for element in valid),
        )

    @staticmethod
    def _image_candidate(element: PptxElement, slide: PptxSlide) -> bool:
        area_ratio = (element.width * element.height) / max(slide.width * slide.height, 1)
        if area_ratio > 0.55:
            return False
        return element.width > 0 and element.height > 0

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

    @classmethod
    def _looks_like_product_name(cls, text: str) -> bool:
        cleaned = " ".join(text.strip().split())
        if len(cleaned) < 3 or len(cleaned) > 140:
            return False
        upper = cleaned.upper()
        if any(token in upper for token in cls.BLOCKED):
            return False
        if CURRENCY_RE.fullmatch(cleaned) or INTEGER_RE.fullmatch(cleaned) or CENTS_RE.fullmatch(cleaned):
            return False
        if UNIT_RE.fullmatch(cleaned):
            return False
        letters = sum(character.isalpha() for character in cleaned)
        if letters < 3:
            return False
        # Single-word produce names such as MELANCIA are valid in the SR corpus.
        return True

    @staticmethod
    def _clean(text: str) -> str:
        return " ".join(str(text or "").strip().split())

    @staticmethod
    def _center(element: PptxElement) -> tuple[float, float]:
        return element.x + element.width / 2.0, element.y + element.height / 2.0
