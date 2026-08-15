from __future__ import annotations

from dataclasses import dataclass

from srstudio.core.models import ProductCard
from srstudio.editor.layout import Rect


@dataclass(frozen=True, slots=True)
class Handle:
    name: str
    x: float
    y: float


class SelectionGeometry:
    """Geometria para seleção por área, handles e rotação."""

    HANDLE_NAMES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

    @staticmethod
    def marquee(cards: list[ProductCard], rect: Rect, contained: bool = False) -> list[str]:
        selected: list[str] = []
        for card in cards:
            if bool(card.overrides.get("hidden", False)):
                continue
            card_rect = Rect(card.x, card.y, card.width, card.height)
            if contained:
                inside = (
                    card_rect.x >= rect.x
                    and card_rect.y >= rect.y
                    and card_rect.right <= rect.right
                    and card_rect.bottom <= rect.bottom
                )
            else:
                inside = card_rect.intersects(rect)
            if inside:
                selected.append(card.id)
        return selected

    @staticmethod
    def handles(card: ProductCard) -> tuple[Handle, ...]:
        x, y, w, h = card.x, card.y, card.width, card.height
        cx, cy = x + w / 2, y + h / 2
        return (
            Handle("nw", x, y),
            Handle("n", cx, y),
            Handle("ne", x + w, y),
            Handle("e", x + w, cy),
            Handle("se", x + w, y + h),
            Handle("s", cx, y + h),
            Handle("sw", x, y + h),
            Handle("w", x, cy),
        )

    @staticmethod
    def resize_from_handle(card: ProductCard, handle: str, dx: float, dy: float, min_size: float = 40.0) -> None:
        if card.locked:
            return
        x, y, w, h = card.x, card.y, card.width, card.height
        if "w" in handle:
            new_w = max(min_size, w - dx)
            card.x = x + (w - new_w)
            card.width = new_w
        if "e" in handle:
            card.width = max(min_size, w + dx)
        if "n" in handle:
            new_h = max(min_size, h - dy)
            card.y = y + (h - new_h)
            card.height = new_h
        if "s" in handle:
            card.height = max(min_size, h + dy)

    @staticmethod
    def rotate(card: ProductCard, delta_degrees: float, snap_degrees: float | None = 15.0) -> None:
        if card.locked:
            return
        value = (card.rotation + delta_degrees) % 360.0
        if snap_degrees and snap_degrees > 0:
            value = round(value / snap_degrees) * snap_degrees
        card.rotation = value % 360.0
