from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin
from typing import Iterable

from .model import CoordinateUnit, GraphicsNode, GraphicsPage, Rect


@dataclass(slots=True)
class ViewportTransform:
    """Transformação visual. Nunca modifica coordenadas persistidas da página."""

    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    def __post_init__(self) -> None:
        self.zoom = max(0.01, float(self.zoom))

    def document_to_screen(self, x: float, y: float) -> tuple[float, float]:
        return x * self.zoom + self.pan_x, y * self.zoom + self.pan_y

    def screen_to_document(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.pan_x) / self.zoom, (y - self.pan_y) / self.zoom

    def rect_to_screen(self, rect: Rect) -> Rect:
        x, y = self.document_to_screen(rect.x, rect.y)
        return Rect(x, y, rect.width * self.zoom, rect.height * self.zoom)

    def pan(self, dx_screen: float, dy_screen: float) -> None:
        self.pan_x += float(dx_screen)
        self.pan_y += float(dy_screen)

    def zoom_at(self, factor: float, screen_x: float, screen_y: float, *, minimum: float = 0.05, maximum: float = 8.0) -> None:
        doc_x, doc_y = self.screen_to_document(screen_x, screen_y)
        self.zoom = min(maximum, max(minimum, self.zoom * float(factor)))
        self.pan_x = screen_x - doc_x * self.zoom
        self.pan_y = screen_y - doc_y * self.zoom


@dataclass(slots=True)
class SnapSettings:
    enabled: bool = True
    snap_page: bool = True
    snap_objects: bool = True
    snap_guides: bool = True
    grid_enabled: bool = False
    grid_spacing: float = 10.0
    tolerance_screen_px: float = 7.0


@dataclass(slots=True)
class SnapResult:
    dx: float
    dy: float
    guide_x: float | None = None
    guide_y: float | None = None
    source_x: str = ""
    source_y: str = ""


class SnapEngine:
    @staticmethod
    def snap_move(page: GraphicsPage, node_ids: Iterable[str], dx: float, dy: float, *, zoom: float = 1.0, settings: SnapSettings | None = None) -> SnapResult:
        settings = settings or SnapSettings()
        if not settings.enabled:
            return SnapResult(float(dx), float(dy))
        ids = {nid for nid in node_ids if nid in page.nodes}
        bounds = page.bounds(ids)
        if bounds is None:
            return SnapResult(float(dx), float(dy))
        moved = bounds.translated(float(dx), float(dy))
        tolerance = max(0.05, settings.tolerance_screen_px / max(zoom, 0.01))
        x_targets, y_targets = SnapEngine._targets(page, ids, settings)
        x_points = ((moved.x, "left"), (moved.center_x, "center"), (moved.right, "right"))
        y_points = ((moved.y, "top"), (moved.center_y, "middle"), (moved.bottom, "bottom"))
        best_x = SnapEngine._best_axis(x_points, x_targets, tolerance)
        best_y = SnapEngine._best_axis(y_points, y_targets, tolerance)
        out_dx = float(dx) + (best_x[0] if best_x else 0.0)
        out_dy = float(dy) + (best_y[0] if best_y else 0.0)
        if settings.grid_enabled and settings.grid_spacing > 0:
            if best_x is None:
                grid = settings.grid_spacing; snapped = round(moved.x / grid) * grid
                if abs(snapped - moved.x) <= tolerance:
                    out_dx += snapped - moved.x; best_x = (snapped - moved.x, snapped, "grid:left")
            if best_y is None:
                grid = settings.grid_spacing; snapped = round(moved.y / grid) * grid
                if abs(snapped - moved.y) <= tolerance:
                    out_dy += snapped - moved.y; best_y = (snapped - moved.y, snapped, "grid:top")
        return SnapResult(out_dx, out_dy, guide_x=best_x[1] if best_x else None, guide_y=best_y[1] if best_y else None, source_x=best_x[2] if best_x else "", source_y=best_y[2] if best_y else "")

    @staticmethod
    def _targets(page: GraphicsPage, excluded: set[str], settings: SnapSettings) -> tuple[list[tuple[float, str]], list[tuple[float, str]]]:
        xs: list[tuple[float, str]] = []; ys: list[tuple[float, str]] = []
        if settings.snap_page:
            xs.extend(((0.0, "page:left"), (page.width / 2.0, "page:center"), (page.width, "page:right")))
            ys.extend(((0.0, "page:top"), (page.height / 2.0, "page:middle"), (page.height, "page:bottom")))
        if settings.snap_guides:
            xs.extend((float(value), "guide") for value in page.guides_x); ys.extend((float(value), "guide") for value in page.guides_y)
        if settings.snap_objects:
            for node in page.nodes.values():
                if node.id in excluded or not node.visible: continue
                rect = node.rect
                xs.extend(((rect.x, f"{node.id}:left"), (rect.center_x, f"{node.id}:center"), (rect.right, f"{node.id}:right")))
                ys.extend(((rect.y, f"{node.id}:top"), (rect.center_y, f"{node.id}:middle"), (rect.bottom, f"{node.id}:bottom")))
        return xs, ys

    @staticmethod
    def _best_axis(points: Iterable[tuple[float, str]], targets: Iterable[tuple[float, str]], tolerance: float) -> tuple[float, float, str] | None:
        best: tuple[float, float, str] | None = None; best_abs = tolerance + 1.0
        for point, point_name in points:
            for target, target_name in targets:
                delta = target - point; distance = abs(delta)
                if distance < best_abs:
                    best_abs = distance; best = (delta, target, f"{target_name}->{point_name}")
        return best if best_abs <= tolerance else None


def hit_test(page: GraphicsPage, x: float, y: float, *, include_locked: bool = True) -> GraphicsNode | None:
    for node in sorted(page.nodes.values(), key=lambda item: (item.z_index, item.id), reverse=True):
        if not node.visible or (node.locked and not include_locked): continue
        if _point_in_node(node, float(x), float(y)): return node
    return None


def _point_in_node(node: GraphicsNode, x: float, y: float) -> bool:
    t = node.transform
    if not t.width or not t.height: return False
    cx = t.x + t.width * t.pivot_x; cy = t.y + t.height * t.pivot_y; angle = radians(-t.rotation)
    dx, dy = x - cx, y - cy
    local_x = dx * cos(angle) - dy * sin(angle) + cx; local_y = dx * sin(angle) + dy * cos(angle) + cy
    return t.x <= local_x <= t.x + t.width and t.y <= local_y <= t.y + t.height


def ruler_step(zoom: float, unit: CoordinateUnit = CoordinateUnit.PIXEL) -> float:
    target_screen = 72.0; raw = target_screen / max(zoom, 0.01); bases = (1.0, 2.0, 5.0, 10.0); magnitude = 1.0
    while raw > 10.0: raw /= 10.0; magnitude *= 10.0
    while raw < 1.0: raw *= 10.0; magnitude /= 10.0
    best = min(bases, key=lambda base: abs(base - raw)) * magnitude
    if unit is CoordinateUnit.MILLIMETER: return max(1.0, best)
    return max(0.5, best)
