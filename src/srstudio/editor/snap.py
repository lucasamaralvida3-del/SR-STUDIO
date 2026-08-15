from __future__ import annotations

from dataclasses import dataclass

from srstudio.editor.layout import Rect


@dataclass(frozen=True, slots=True)
class Guide:
    axis: str
    position: float
    kind: str


@dataclass(frozen=True, slots=True)
class SnapResult:
    x: float
    y: float
    guides: tuple[Guide, ...] = ()


class SnapEngine:
    """Snapping determinístico para bordas, centros, grid e página."""

    def __init__(self, tolerance: float = 8.0, grid: float = 10.0) -> None:
        self.tolerance = max(0.0, tolerance)
        self.grid = max(1.0, grid)

    def snap(self, moving: Rect, others: list[Rect], page_width: float, page_height: float) -> SnapResult:
        x, y = moving.x, moving.y
        guides: list[Guide] = []

        x_candidates = [
            (0.0, moving.x, "page-left"),
            (page_width, moving.right, "page-right"),
            (page_width / 2, moving.x + moving.width / 2, "page-center"),
        ]
        y_candidates = [
            (0.0, moving.y, "page-top"),
            (page_height, moving.bottom, "page-bottom"),
            (page_height / 2, moving.y + moving.height / 2, "page-center"),
        ]

        for other in others:
            x_candidates.extend(
                [
                    (other.x, moving.x, "left-left"),
                    (other.right, moving.right, "right-right"),
                    (other.x + other.width / 2, moving.x + moving.width / 2, "center-x"),
                    (other.right, moving.x, "left-right"),
                    (other.x, moving.right, "right-left"),
                ]
            )
            y_candidates.extend(
                [
                    (other.y, moving.y, "top-top"),
                    (other.bottom, moving.bottom, "bottom-bottom"),
                    (other.y + other.height / 2, moving.y + moving.height / 2, "center-y"),
                    (other.bottom, moving.y, "top-bottom"),
                    (other.y, moving.bottom, "bottom-top"),
                ]
            )

        best_x = min(x_candidates, key=lambda item: abs(item[0] - item[1]))
        if abs(best_x[0] - best_x[1]) <= self.tolerance:
            x += best_x[0] - best_x[1]
            guides.append(Guide("x", best_x[0], best_x[2]))
        else:
            grid_x = round(x / self.grid) * self.grid
            if abs(grid_x - x) <= self.tolerance / 2:
                x = grid_x
                guides.append(Guide("x", grid_x, "grid"))

        best_y = min(y_candidates, key=lambda item: abs(item[0] - item[1]))
        if abs(best_y[0] - best_y[1]) <= self.tolerance:
            y += best_y[0] - best_y[1]
            guides.append(Guide("y", best_y[0], best_y[2]))
        else:
            grid_y = round(y / self.grid) * self.grid
            if abs(grid_y - y) <= self.tolerance / 2:
                y = grid_y
                guides.append(Guide("y", grid_y, "grid"))

        x = min(max(0.0, x), max(0.0, page_width - moving.width))
        y = min(max(0.0, y), max(0.0, page_height - moving.height))
        return SnapResult(x, y, tuple(guides))
