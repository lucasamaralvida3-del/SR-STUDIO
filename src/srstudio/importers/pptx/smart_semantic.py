from __future__ import annotations

from .reader import PptxElement, PptxSlide
from .semantic import PriceCluster, SemanticCard, SemanticMapper


class SmartSlotSemanticMapper(SemanticMapper):
    """Stricter semantic mapper used only for destructive/editable slot binding.

    Training can tolerate a broad candidate radius. Editing cannot: a distant
    name/image match may cause one drag/drop action to rewrite another product.
    """

    NAME_MAX_DX = 0.17
    NAME_MAX_DY = 0.27
    IMAGE_MAX_DX = 0.17
    IMAGE_MAX_DY = 0.27

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
                if dx > self.NAME_MAX_DX or dy > self.NAME_MAX_DY:
                    continue
                # Names are normally above/around the price. Penalize names well
                # below the price so another row is not consumed accidentally.
                directional = 0.0 if dy_signed <= 0.035 else dy_signed * 1.8
                score = dx * 1.65 + dy * 1.05 + directional
            else:
                if dx > self.IMAGE_MAX_DX or dy > self.IMAGE_MAX_DY:
                    continue
                area_ratio = (candidate.width * candidate.height) / max(slide.width * slide.height, 1)
                if area_ratio > 0.14:
                    continue
                score = dx * 1.2 + dy + max(0.0, area_ratio - 0.08) * 2.5
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
            # A second price must clearly belong to the same visual card. The old
            # radius could accidentally absorb the price from a neighboring item.
            if dx <= 0.10 and dy <= 0.075:
                score = dx + dy * 1.2
                if best is None or score < best[0]:
                    best = (score, card)
        return best[1] if best is not None else None

    @staticmethod
    def _image_candidate(element: PptxElement, slide: PptxSlide) -> bool:
        if element.width <= 0 or element.height <= 0:
            return False
        sw = max(slide.width, 1)
        sh = max(slide.height, 1)
        area_ratio = (element.width * element.height) / max(sw * sh, 1)
        if area_ratio > 0.14:
            return False
        if element.width / sw > 0.42 or element.height / sh > 0.48:
            return False
        return True
