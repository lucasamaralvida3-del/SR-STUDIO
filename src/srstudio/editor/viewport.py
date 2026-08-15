from __future__ import annotations

from dataclasses import dataclass

from srstudio.editor.layout import Rect


@dataclass(frozen=True, slots=True)
class ViewportTransform:
    page_width: float
    page_height: float
    viewport_width: float
    viewport_height: float
    padding: float = 28.0
    zoom: float = 1.0

    @property
    def scale(self) -> float:
        usable_w = max(1.0, self.viewport_width - self.padding * 2)
        usable_h = max(1.0, self.viewport_height - self.padding * 2)
        fit = min(usable_w / max(self.page_width, 1.0), usable_h / max(self.page_height, 1.0))
        return max(0.05, fit * self.zoom)

    @property
    def origin(self) -> tuple[float, float]:
        width = self.page_width * self.scale
        height = self.page_height * self.scale
        return ((self.viewport_width - width) / 2.0, (self.viewport_height - height) / 2.0)

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self.origin
        return ox + x * self.scale, oy + y * self.scale

    def to_page(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self.origin
        return (x - ox) / self.scale, (y - oy) / self.scale

    def rect_to_screen(self, rect: Rect) -> Rect:
        x, y = self.to_screen(rect.x, rect.y)
        return Rect(x, y, rect.width * self.scale, rect.height * self.scale)

    def page_bounds(self) -> Rect:
        ox, oy = self.origin
        return Rect(ox, oy, self.page_width * self.scale, self.page_height * self.scale)


def contains(rect: Rect, x: float, y: float) -> bool:
    return rect.x <= x <= rect.right and rect.y <= y <= rect.bottom


def resize_handle(rect: Rect, size: float = 10.0) -> Rect:
    return Rect(rect.right - size / 2, rect.bottom - size / 2, size, size)
