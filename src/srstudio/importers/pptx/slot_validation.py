from __future__ import annotations

from dataclasses import dataclass

from .reader import PptxElement, PptxSlide
from .semantic import SemanticCard


@dataclass(frozen=True, slots=True)
class SlotValidationStats:
    detected: int
    accepted: int
    rejected: int


class SmartSlotValidator:
    """Conservative gate between semantic recognition and editable Canva slots.

    The semantic mapper is intentionally permissive because it is also used for
    learning. The editor must be stricter: a false positive can replace artwork
    from several products at once. This validator therefore prefers no slot over
    an ambiguous/oversized slot.
    """

    MIN_CONFIDENCE = 0.68
    MAX_SLOT_AREA = 0.18
    MAX_SLOT_WIDTH = 0.52
    MAX_SLOT_HEIGHT = 0.48
    MAX_NAME_DX = 0.18
    MAX_NAME_DY = 0.30
    MAX_IMAGE_DX = 0.18
    MAX_IMAGE_DY = 0.30
    MAX_IMAGE_AREA = 0.12
    MAX_IMAGE_WIDTH = 0.38
    MAX_IMAGE_HEIGHT = 0.42
    MAX_SECONDARY_DX = 0.14
    MAX_SECONDARY_DY = 0.11
    MAX_OVERLAP_IOU = 0.42

    @classmethod
    def select(cls, candidates: list[SemanticCard], slide: PptxSlide) -> tuple[list[SemanticCard], SlotValidationStats]:
        prepared: list[SemanticCard] = []
        for candidate in candidates:
            if cls._prepare(candidate, slide):
                prepared.append(candidate)

        prepared.sort(key=lambda item: item.confidence, reverse=True)
        accepted: list[SemanticCard] = []
        used_elements: set[int] = set()
        for candidate in prepared:
            element_ids = {id(item) for item in cls._semantic_elements(candidate)}
            if element_ids & used_elements:
                continue
            if any(cls._iou(candidate.bounds, other.bounds) > cls.MAX_OVERLAP_IOU for other in accepted):
                continue
            accepted.append(candidate)
            used_elements.update(element_ids)

        accepted.sort(key=lambda item: (item.bounds[1], item.bounds[0]) if item.bounds else (0, 0))
        return accepted, SlotValidationStats(
            detected=len(candidates),
            accepted=len(accepted),
            rejected=max(0, len(candidates) - len(accepted)),
        )

    @classmethod
    def _prepare(cls, candidate: SemanticCard, slide: PptxSlide) -> bool:
        cluster = candidate.price_cluster
        anchor = cluster.anchor if cluster is not None else candidate.price
        if anchor is None or candidate.price_value is None or candidate.name is None:
            return False
        if candidate.confidence < cls.MIN_CONFIDENCE:
            return False
        if not cls._has_usable_price(candidate):
            return False
        if not cls._near(anchor, candidate.name, slide, cls.MAX_NAME_DX, cls.MAX_NAME_DY):
            return False

        if candidate.image is not None:
            if cls._unsafe_image(candidate.image, slide) or not cls._near(
                anchor,
                candidate.image,
                slide,
                cls.MAX_IMAGE_DX,
                cls.MAX_IMAGE_DY,
            ):
                candidate.image = None

        if candidate.secondary_price is not None:
            secondary_anchor = candidate.secondary_price.anchor
            if secondary_anchor is None or not cls._near(
                anchor,
                secondary_anchor,
                slide,
                cls.MAX_SECONDARY_DX,
                cls.MAX_SECONDARY_DY,
            ):
                candidate.secondary_price = None

        elements = cls._semantic_elements(candidate)
        bounds = cls._bounds(elements)
        if bounds is None:
            return False

        pad_x = max(2, int(slide.width * 0.008))
        pad_y = max(2, int(slide.height * 0.008))
        left, top, right, bottom = bounds
        bounds = (
            max(0, left - pad_x),
            max(0, top - pad_y),
            min(slide.width, right + pad_x),
            min(slide.height, bottom + pad_y),
        )
        if not cls._safe_geometry(bounds, slide):
            return False

        candidate.bounds = bounds
        return True

    @staticmethod
    def _has_usable_price(candidate: SemanticCard) -> bool:
        cluster = candidate.price_cluster
        if cluster is None:
            return candidate.price is not None and candidate.price_value is not None
        if cluster.complete is not None:
            return True
        return cluster.integer is not None and cluster.cents is not None

    @classmethod
    def _unsafe_image(cls, element: PptxElement, slide: PptxSlide) -> bool:
        sw = max(slide.width, 1)
        sh = max(slide.height, 1)
        area = (element.width * element.height) / max(sw * sh, 1)
        return (
            area > cls.MAX_IMAGE_AREA
            or element.width / sw > cls.MAX_IMAGE_WIDTH
            or element.height / sh > cls.MAX_IMAGE_HEIGHT
        )

    @staticmethod
    def _near(origin: PptxElement, candidate: PptxElement, slide: PptxSlide, max_dx: float, max_dy: float) -> bool:
        ox = origin.x + origin.width / 2
        oy = origin.y + origin.height / 2
        cx = candidate.x + candidate.width / 2
        cy = candidate.y + candidate.height / 2
        dx = abs(cx - ox) / max(slide.width, 1)
        dy = abs(cy - oy) / max(slide.height, 1)
        return dx <= max_dx and dy <= max_dy

    @classmethod
    def _safe_geometry(cls, bounds: tuple[int, int, int, int], slide: PptxSlide) -> bool:
        left, top, right, bottom = bounds
        width = max(0, right - left)
        height = max(0, bottom - top)
        if width <= 0 or height <= 0:
            return False
        sw = max(slide.width, 1)
        sh = max(slide.height, 1)
        area = (width * height) / max(sw * sh, 1)
        return (
            area <= cls.MAX_SLOT_AREA
            and width / sw <= cls.MAX_SLOT_WIDTH
            and height / sh <= cls.MAX_SLOT_HEIGHT
        )

    @staticmethod
    def _bounds(elements: list[PptxElement]) -> tuple[int, int, int, int] | None:
        valid = [item for item in elements if item.width > 0 and item.height > 0]
        if not valid:
            return None
        return (
            min(item.x for item in valid),
            min(item.y for item in valid),
            max(item.x + item.width for item in valid),
            max(item.y + item.height for item in valid),
        )

    @staticmethod
    def _semantic_elements(candidate: SemanticCard) -> list[PptxElement]:
        items: list[PptxElement] = []
        if candidate.name is not None:
            items.append(candidate.name)
        if candidate.image is not None:
            items.append(candidate.image)
        if candidate.price_cluster is not None:
            items.extend(candidate.price_cluster.elements)
        elif candidate.price is not None:
            items.append(candidate.price)
        if candidate.secondary_price is not None:
            items.extend(candidate.secondary_price.elements)
        unique: list[PptxElement] = []
        seen: set[int] = set()
        for item in items:
            if id(item) not in seen:
                seen.add(id(item))
                unique.append(item)
        return unique

    @staticmethod
    def _iou(first: tuple[int, int, int, int] | None, second: tuple[int, int, int, int] | None) -> float:
        if first is None or second is None:
            return 0.0
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        intersection = iw * ih
        if intersection <= 0:
            return 0.0
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - intersection
        return intersection / union if union > 0 else 0.0
