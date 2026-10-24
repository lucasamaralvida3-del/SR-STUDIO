from __future__ import annotations

"""Beta 44 promotional compositions in normalized page coordinates.

The header remains empty for an independently placed campaign logo. This is
a pure geometry planner: no state is changed until the editor applies a plan.
"""

from dataclasses import dataclass
from math import ceil
from typing import Literal

LayoutKind = Literal["individual", "six", "seven", "eleven", "auto"]


@dataclass(frozen=True)
class SlotPlacement:
    index: int
    x: float
    y: float
    width: float
    height: float
    kind: str

    def as_dict(self) -> dict:
        return vars(self).copy()


@dataclass(frozen=True)
class PromotionPlan:
    mode: str
    logo_reserved: float
    placements: tuple[SlotPlacement, ...]


def _row(start: int, count: int, y: float, h: float, *, left: float = .045,
         width: float = .91, gap: float = .012, kind: str = "individual") -> list[SlotPlacement]:
    each = (width - (count - 1) * gap) / count
    return [SlotPlacement(start + i, left + i * (each + gap), y, each, h, kind)
            for i in range(count)]


def plan_promotion(mode: LayoutKind, *, count: int | None = None,
                   logo_reserved: float = .24, variation: int = 0) -> PromotionPlan:
    """Plan without overlap; all numbers are fractions of the physical page.

    Supported reference compositions: 1, 6, 7 and 11 products. Automatic
    mode also supports 5, and arbitrary counts from 1 to 24.
    """
    presets = {"individual": 1, "six": 6, "seven": 7, "eleven": 11}
    if mode not in (*presets, "auto"):
        raise ValueError("Unknown promotion layout")
    n = presets[mode] if mode != "auto" else (count if count is not None else 6)
    if not isinstance(n, int) or not 1 <= n <= 24:
        raise ValueError("Product count must be between 1 and 24")
    if not 0.15 <= logo_reserved <= .5:
        raise ValueError("Logo reserve must be between 15 and 50 percent")
    top = logo_reserved + .025
    bottom = .975
    available = bottom - top
    items: list[SlotPlacement] = []
    if mode == "individual" or (mode == "auto" and n == 1):
        items = [SlotPlacement(0, .18, top + .04 * available, .64, .91 * available, "individual")]
    elif mode in ("six", "seven"):
        lower_count = 3 if mode == "six" else 4
        split = top + available * .59
        items.append(SlotPlacement(0, .045, top, .43, split - top - .012, "individual"))
        items.extend(_row(1, 2, top, (split - top - .024) / 2, left=.492, width=.463))
        # Second right item occupies the lower half of the upper composition.
        second = items[2]
        items[2] = SlotPlacement(second.index, second.x,
                                 top + (split - top) / 2, second.width,
                                 (split - top) / 2 - .012, second.kind)
        items.extend(_row(3, lower_count, split, bottom - split))
    elif mode == "eleven":
        first = available * .32
        second = available * .32
        items.extend(_row(0, 3, top, first - .01))
        items.extend(_row(3, 3, top + first, second - .01))
        items.extend(_row(6, 5, top + first + second, available - first - second))
    else:
        # Auto: deterministic rotation changes orientation/number of columns,
        # while always preserving the protected logo region.
        columns = max(1, min(n, (3, 4, 5)[variation % 3]))
        rows = ceil(n / columns)
        gap = .012
        row_h = (available - (rows - 1) * gap) / rows
        for row in range(rows):
            row_count = min(columns, n - row * columns)
            items.extend(_row(row * columns, row_count,
                              top + row * (row_h + gap), row_h))
    result = PromotionPlan(mode, logo_reserved, tuple(items))
    for p in result.placements:
        if min(p.width, p.height) <= 0 or p.x < 0 or p.y < logo_reserved or p.x + p.width > 1.000001 or p.y + p.height > 1.000001:
            raise AssertionError("Slot outside promotion area")
    for i, a in enumerate(result.placements):
        for b in result.placements[i + 1:]:
            if a.x < b.x + b.width - 1e-8 and b.x < a.x + a.width - 1e-8 and a.y < b.y + b.height - 1e-8 and b.y < a.y + a.height - 1e-8:
                raise AssertionError("Overlapping promotional slots")
    return result
