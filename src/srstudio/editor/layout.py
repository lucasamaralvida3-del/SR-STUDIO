from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.bottom <= other.y
            or other.bottom <= self.y
        )


@dataclass(frozen=True, slots=True)
class LayoutSlot:
    index: int
    rect: Rect
    role: str = "normal"


@dataclass(frozen=True, slots=True)
class LayoutPlan:
    name: str
    slots: tuple[LayoutSlot, ...]
    score: float


class LayoutEngine:
    """Motor geométrico determinístico para páginas de encarte."""

    def __init__(self, margin: float = 28.0, gap: float = 16.0) -> None:
        self.margin = margin
        self.gap = gap

    def grid(self, count: int, page_width: float, page_height: float, columns: int | None = None) -> LayoutPlan:
        if count <= 0:
            return LayoutPlan("grid", (), 100.0)
        columns = columns or max(1, round(sqrt(count * page_width / max(page_height, 1))))
        rows = ceil(count / columns)
        usable_w = page_width - 2 * self.margin - self.gap * (columns - 1)
        usable_h = page_height - 2 * self.margin - self.gap * (rows - 1)
        cell_w = max(1.0, usable_w / columns)
        cell_h = max(1.0, usable_h / rows)
        slots: list[LayoutSlot] = []
        for i in range(count):
            row, col = divmod(i, columns)
            x = self.margin + col * (cell_w + self.gap)
            y = self.margin + row * (cell_h + self.gap)
            slots.append(LayoutSlot(i, Rect(x, y, cell_w, cell_h)))
        return LayoutPlan(f"grid-{columns}x{rows}", tuple(slots), self._quality(slots, page_width, page_height))

    def hero(self, count: int, page_width: float, page_height: float) -> LayoutPlan:
        if count <= 1:
            return LayoutPlan("hero", (LayoutSlot(0, Rect(self.margin, self.margin, page_width - 2*self.margin, page_height - 2*self.margin), "hero"),) if count else (), 100.0)
        hero_h = (page_height - 2 * self.margin) * 0.38
        slots = [LayoutSlot(0, Rect(self.margin, self.margin, page_width - 2*self.margin, hero_h), "hero")]
        remaining = self.grid(count - 1, page_width, page_height - hero_h - self.gap, columns=None)
        for slot in remaining.slots:
            slots.append(LayoutSlot(slot.index + 1, Rect(slot.rect.x, slot.rect.y + hero_h + self.gap, slot.rect.width, slot.rect.height)))
        return LayoutPlan("hero+grid", tuple(slots), self._quality(slots, page_width, page_height))

    def best(self, count: int, page_width: float, page_height: float, highlighted: int = 0) -> LayoutPlan:
        candidates = [self.grid(count, page_width, page_height)]
        for columns in range(2, min(6, count) + 1):
            candidates.append(self.grid(count, page_width, page_height, columns=columns))
        if highlighted and count:
            candidates.append(self.hero(count, page_width, page_height))
        return max(candidates, key=lambda item: item.score)

    def rebalance(self, total_items: int, page_capacity: int) -> tuple[int, ...]:
        if total_items <= 0:
            return ()
        capacity = max(1, page_capacity)
        pages = ceil(total_items / capacity)
        base, remainder = divmod(total_items, pages)
        return tuple(base + (1 if i < remainder else 0) for i in range(pages))

    def collision_pairs(self, rects: Iterable[Rect]) -> list[tuple[int, int]]:
        items = list(rects)
        collisions: list[tuple[int, int]] = []
        for i, first in enumerate(items):
            for j in range(i + 1, len(items)):
                if first.intersects(items[j]):
                    collisions.append((i, j))
        return collisions

    def _quality(self, slots: Iterable[LayoutSlot], page_width: float, page_height: float) -> float:
        rects = [slot.rect for slot in slots]
        if not rects:
            return 100.0
        collisions = len(self.collision_pairs(rects))
        used = sum(r.width * r.height for r in rects)
        page = max(1.0, page_width * page_height)
        coverage = min(1.0, used / page)
        ratio_penalty = sum(abs((r.width / max(r.height, 1)) - 0.85) for r in rects) / len(rects)
        return round(max(0.0, 100.0 - collisions * 35.0 - ratio_penalty * 8.0 + coverage * 10.0), 2)
