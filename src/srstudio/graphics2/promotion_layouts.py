from __future__ import annotations

"""Layouts are positioning instructions for EXISTING canonical Smart Slots.

Reference Terça Verde:
- 7 offers: one hero Individual, two Slot Único, one real Multi-4 ribbon.
- 11 offers: one larger Slot Único, two smaller, three middle, Multi-5.
Other compositions likewise prefer Slot Único. Individual must be explicit,
never manufactured as a substitute for a unique slot. Nothing here renders
a fake product card, touches binding data or changes the original artwork.
"""

from dataclasses import asdict, dataclass
from math import ceil
from typing import Literal

LayoutKind = Literal["individual", "six", "seven", "nine", "eleven", "custom", "auto"]


@dataclass(frozen=True)
class SlotPlacement:
    index: int
    x: float
    y: float
    width: float
    height: float
    kind: str  # "single" = certified Slot Único, "individual", "multi"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PromotionPlan:
    mode: str
    logo_reserved: float
    placements: tuple[SlotPlacement, ...]


def _row(start: int, count: int, y: float, h: float, *, left: float = .045,
         width: float = .91, gap: float = .012, kind: str = "single") -> list[SlotPlacement]:
    each = (width - (count - 1) * gap) / count
    return [SlotPlacement(start + i, left + i * (each + gap), y, each, h, kind)
            for i in range(count)]


def plan_promotion(mode: LayoutKind, *, count: int | None = None,
                   logo_reserved: float = .24, variation: int = 0) -> PromotionPlan:
    """Plan actual reusable slot families, not cosmetic stand-ins.

    A Multi ribbon is represented as N adjacent positions of kind 'multi'.
    The compositor groups them into exactly ONE resizable Multi-N parent.
    """
    presets = {"individual": 1, "six": 6, "seven": 7, "nine": 9, "eleven": 11, "custom": 10}
    if mode not in (*presets, "auto"):
        raise ValueError("Unknown promotion layout")
    n = (count if count is not None else presets.get(mode, 6))
    if mode in ("individual", "six", "seven", "custom") and n != presets[mode]:
        raise ValueError("Contagem incompatível com o layout selecionado")
    if mode == "nine" and n not in range(6, 10):
        raise ValueError("Layout de nove aceita de 6 a 9 produtos")
    if mode == "eleven" and n not in range(8, 12):
        raise ValueError("Layout de onze aceita de 8 a 11 produtos")
    if not isinstance(n, int) or not 1 <= n <= 24:
        raise ValueError("Product count must be between 1 and 24")
    if not .15 <= logo_reserved <= .50:
        raise ValueError("Logo reserve must be between 15 and 50 percent")
    # Reserve the bottom campaign validity pill as shown in both real photos.
    # The Multi price ribbon must end ABOVE “OFERTAS VÁLIDAS ...”.
    top, bottom = logo_reserved + .025, .93
    height = bottom - top
    items: list[SlotPlacement] = []
    if mode == "individual":
        items = [SlotPlacement(0, .19, top + .03 * height, .62,
                               .92 * height, "individual")]
    elif mode == "custom":
        items = [SlotPlacement(0, .045, top, .42, .64 * height, "individual")]
        for index in range(3):
            items.append(SlotPlacement(index + 1, .50,
                                       top + index * .22 * height,
                                       .455, .20 * height, "single"))
        items.extend(_row(4, 6, top + .72 * height, .28 * height, kind="multi"))
    elif mode == "seven":
        # Reference image 1: Individual grande + 2 Únicos à direita
        # + one CONTINUOUS genuine 4-product ribbon below.
        ribbon = top + .735 * height
        left_w, right_x, right_w = .525, .605, .35
        items.append(SlotPlacement(0, .045, top, left_w,
                                   ribbon - top - .012, "individual"))
        right_h = (ribbon - top - .012) / 2
        items.extend([
            SlotPlacement(1, right_x, top, right_w, right_h - .006, "single"),
            SlotPlacement(2, right_x, top + right_h + .006,
                          right_w, right_h - .006, "single"),
        ])
        items.extend(_row(3, 4, ribbon, bottom - ribbon, kind="multi"))
    elif mode == "eleven":
        # Reference image 2: one LARGE Único + 2 smaller Únicos,
        # then 3 equally sized Únicos + a real Multi-5.
        split1 = top + .425 * height
        split2 = top + .765 * height
        items.extend([
            SlotPlacement(0, .045, top, .37, split1 - top - .010, "single"),
            SlotPlacement(1, .432, top + .035 * height, .245,
                          split1 - top - .045 * height, "single"),
            SlotPlacement(2, .695, top + .035 * height, .26,
                          split1 - top - .045 * height, "single"),
        ])
        items.extend(_row(3, 3, split1, split2 - split1 - .012))
        items.extend(_row(6, n - 6, split2, bottom - split2, kind="multi"))
    elif mode == "nine":
        # Primary Único and three medium Únicos above one Multi-5.
        split = top + .705 * height
        items.append(SlotPlacement(0, .045, top, .41, split - top - .012, "single"))
        items.extend([
            SlotPlacement(1, .477, top, .215, (split - top) * .46, "single"),
            SlotPlacement(2, .712, top, .243, (split - top) * .46, "single"),
            SlotPlacement(3, .557, top + (split-top) * .49, .32,
                          (split-top) * .49, "single"),
        ])
        items.extend(_row(4, n - 4, split, bottom - split, kind="multi"))
    elif mode == "six":
        # Six Únicos, not the six Individual cards from the old Beta44 mock.
        gap = .014
        row_h = (height - gap) / 2
        items.extend(_row(0, 3, top, row_h))
        items.extend(_row(3, 3, top + row_h + gap, row_h))
    elif n == 1:
        items = [SlotPlacement(0, .205, top + .13 * height, .59,
                               .75 * height, "single")]
    else:
        # Auto: use Únicos by default, with stable spacing. No fake price cards.
        columns = max(1, min(n, (3, 4, 5)[variation % 3]))
        rows = ceil(n / columns)
        gap = .012
        row_h = (height - (rows - 1) * gap) / rows
        for row in range(rows):
            row_count = min(columns, n - row * columns)
            items.extend(_row(row * columns, row_count,
                              top + row * (row_h + gap), row_h))
    result = PromotionPlan(mode, logo_reserved, tuple(items))
    if len(result.placements) != n or [p.index for p in items] != list(range(n)):
        raise AssertionError("Promoção possui posições faltantes ou duplicadas")
    for p in items:
        if (p.kind not in {"single", "individual", "multi"} or
                min(p.width, p.height) <= 0 or p.x < 0 or
                p.y < logo_reserved or p.x + p.width > 1.000001 or
                p.y + p.height > 1.000001):
            raise AssertionError("Slot fora do encarte")
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if (a.x < b.x + b.width - 1e-8 and b.x < a.x + a.width - 1e-8 and
                    a.y < b.y + b.height - 1e-8 and b.y < a.y + a.height - 1e-8):
                raise AssertionError("Smart Slots sobrepostos")
    multi = [p for p in items if p.kind == "multi"]
    if multi:
        if not 2 <= len(multi) <= 8 or [p.index for p in multi] != list(range(multi[0].index, n)):
            raise AssertionError("Multi exige 2 a 8 posições consecutivas no final")
    return result
