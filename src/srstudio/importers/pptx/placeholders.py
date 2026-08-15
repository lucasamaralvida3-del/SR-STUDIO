from __future__ import annotations

from .reader import PptxElement, PptxSlide
from .semantic import SemanticCard


class CanvaImagePlaceholderDetector:
    """Locate empty Canva product-card artwork that can safely receive an image.

    Many SR Canva exports intentionally contain a white product card but no product
    photo. The card itself must stay because price/name artwork is layered around it;
    this detector only derives the free upper region where a product image can be
    composited without covering the price.
    """

    PLACEHOLDER_FILLS = {"#FFFFFF", "theme:lt1", "theme:bg1"}
    MIN_AREA = 0.012
    MAX_AREA = 0.065
    MIN_WIDTH = 0.11
    MAX_WIDTH = 0.32
    MIN_HEIGHT = 0.08
    MAX_HEIGHT = 0.24
    MAX_CENTER_DX = 0.19
    MAX_CENTER_DY = 0.22

    @classmethod
    def find(
        cls,
        candidate: SemanticCard,
        slide: PptxSlide,
        used_ids: set[int] | None = None,
    ) -> PptxElement | None:
        anchor = candidate.price_cluster.anchor if candidate.price_cluster is not None else candidate.price
        if anchor is None:
            return None
        used = used_ids or set()
        ax, ay = cls._center(anchor)
        sw = max(slide.width, 1)
        sh = max(slide.height, 1)
        best: tuple[float, PptxElement] | None = None
        for element in slide.elements:
            if id(element) in used or not cls._is_placeholder(element, slide):
                continue
            cx, cy = cls._center(element)
            dx = abs(cx - ax) / sw
            dy = abs(cy - ay) / sh
            if dx > cls.MAX_CENTER_DX or dy > cls.MAX_CENTER_DY:
                continue
            # A product card normally contains or ends very close to the price.
            price_inside_y = element.y - int(sh * 0.025) <= ay <= element.y + element.height + int(sh * 0.045)
            if not price_inside_y:
                continue
            horizontal_overlap = cls._axis_overlap(
                anchor.x,
                anchor.x + anchor.width,
                element.x,
                element.x + element.width,
            )
            if horizontal_overlap <= 0:
                continue
            score = dx * 1.8 + dy + (0.0 if element.y <= ay else 0.18)
            if best is None or score < best[0]:
                best = (score, element)
        return best[1] if best is not None else None

    @classmethod
    def image_box(
        cls,
        placeholder: PptxElement,
        candidate: SemanticCard,
        slide: PptxSlide,
    ) -> tuple[int, int, int, int] | None:
        """Return a safe image-only sub-rectangle inside a product card."""
        left = placeholder.x
        top = placeholder.y
        right = placeholder.x + placeholder.width
        bottom = placeholder.y + placeholder.height
        if right <= left or bottom <= top:
            return None

        price_elements = []
        if candidate.price_cluster is not None:
            price_elements.extend(candidate.price_cluster.elements)
        elif candidate.price is not None:
            price_elements.append(candidate.price)
        price_bounds = cls._bounds(price_elements)

        inset_x = max(2, round(placeholder.width * 0.055))
        inset_top = max(2, round(placeholder.height * 0.045))
        image_left = left + inset_x
        image_right = right - inset_x
        image_top = top + inset_top

        # Keep a clear gap above the price. When price geometry is unusual, use
        # the upper 58% of the white card rather than risking price obstruction.
        fallback_bottom = top + round(placeholder.height * 0.58)
        image_bottom = fallback_bottom
        if price_bounds is not None:
            _, price_top, _, _ = price_bounds
            gap = max(2, round(slide.height * 0.006))
            if top < price_top < bottom:
                image_bottom = min(fallback_bottom, price_top - gap)

        min_height = max(8, round(slide.height * 0.026))
        if image_bottom - image_top < min_height:
            image_bottom = min(bottom - max(2, round(placeholder.height * 0.08)), image_top + min_height)
        if image_right <= image_left or image_bottom <= image_top:
            return None
        return image_left, image_top, image_right, image_bottom

    @classmethod
    def expand_candidate_bounds(
        cls,
        candidate: SemanticCard,
        placeholder: PptxElement,
        slide: PptxSlide,
    ) -> None:
        if candidate.bounds is None:
            return
        left, top, right, bottom = candidate.bounds
        candidate.bounds = (
            max(0, min(left, placeholder.x)),
            max(0, min(top, placeholder.y)),
            min(slide.width, max(right, placeholder.x + placeholder.width)),
            min(slide.height, max(bottom, placeholder.y + placeholder.height)),
        )

    @classmethod
    def _is_placeholder(cls, element: PptxElement, slide: PptxSlide) -> bool:
        if element.kind != "shape" or element.text.strip():
            return False
        fill = str(element.metadata.get("fill") or "")
        if fill not in cls.PLACEHOLDER_FILLS:
            return False
        sw = max(slide.width, 1)
        sh = max(slide.height, 1)
        wr = element.width / sw
        hr = element.height / sh
        area = (element.width * element.height) / max(sw * sh, 1)
        return (
            cls.MIN_AREA <= area <= cls.MAX_AREA
            and cls.MIN_WIDTH <= wr <= cls.MAX_WIDTH
            and cls.MIN_HEIGHT <= hr <= cls.MAX_HEIGHT
        )

    @staticmethod
    def _center(element: PptxElement) -> tuple[float, float]:
        return element.x + element.width / 2, element.y + element.height / 2

    @staticmethod
    def _axis_overlap(a1: float, a2: float, b1: float, b2: float) -> float:
        return max(0.0, min(a2, b2) - max(a1, b1))

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
