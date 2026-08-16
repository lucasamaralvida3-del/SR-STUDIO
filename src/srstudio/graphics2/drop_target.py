from __future__ import annotations

"""Resolução espacial de Smart Slots para drag-and-drop de produtos.

O editor pode receber um produto em coordenadas do documento sem conhecer a
estrutura interna do template. A resolução prioriza ProductCards semânticos,
usa os nodes do Smart Slot como fallback e escolhe o alvo mais específico em
caso de sobreposição.
"""

from dataclasses import dataclass
from math import hypot

from .model import GraphicsPage, Rect, SmartSlot
from .semantic_blocks import semantic_block


@dataclass(slots=True, frozen=True)
class DropTarget:
    slot_id: str
    bounds: Rect
    inside: bool
    distance: float
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "bounds": {
                "x": self.bounds.x,
                "y": self.bounds.y,
                "width": self.bounds.width,
                "height": self.bounds.height,
            },
            "inside": self.inside,
            "distance": self.distance,
            "confidence": self.confidence,
        }


def smart_slot_bounds(page: GraphicsPage, slot: SmartSlot) -> Rect | None:
    """Retorna a área visual mais representativa de um Smart Slot."""

    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    card = semantic_block(page, card_id) if card_id else None
    if card:
        raw = card.get("bounds")
        if isinstance(raw, dict):
            width = max(0.0, float(raw.get("width") or 0.0))
            height = max(0.0, float(raw.get("height") or 0.0))
            if width > 0 and height > 0:
                return Rect(
                    float(raw.get("x") or 0.0),
                    float(raw.get("y") or 0.0),
                    width,
                    height,
                )

    node_ids: list[str] = [str(node_id) for node_id in slot.node_by_role.values() if node_id]
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for values in extras.values():
            if isinstance(values, (list, tuple)):
                node_ids.extend(str(node_id) for node_id in values if node_id)
    unique = list(dict.fromkeys(node_ids))
    return page.bounds(unique)


def find_drop_target(
    page: GraphicsPage,
    x: float,
    y: float,
    *,
    magnet_distance: float = 0.0,
) -> DropTarget | None:
    """Resolve o Smart Slot que deve receber um produto solto no canvas.

    Alvos contendo o ponto sempre vencem. Se houver sobreposição, o menor card
    é considerado mais específico; confiança desempata. ``magnet_distance``
    permite aceitar um drop muito próximo da borda sem capturar áreas distantes.
    """

    px = float(x)
    py = float(y)
    magnet = max(0.0, float(magnet_distance))
    candidates: list[tuple[tuple[float, float, float, str], DropTarget]] = []
    for slot in page.slots.values():
        if slot.locked:
            continue
        bounds = smart_slot_bounds(page, slot)
        if bounds is None or bounds.width <= 0 or bounds.height <= 0:
            continue
        normalized = bounds.normalized()
        inside = _contains(normalized, px, py)
        distance = 0.0 if inside else _distance_to_rect(normalized, px, py)
        if not inside and (magnet <= 0.0 or distance > magnet):
            continue
        target = DropTarget(
            slot_id=slot.id,
            bounds=normalized,
            inside=inside,
            distance=distance,
            confidence=max(0.0, min(1.0, float(slot.confidence))),
        )
        area = normalized.width * normalized.height
        # Dentro > magnetizado; depois menor área > maior confiança > distância.
        rank = (0.0 if inside else 1.0, area, -target.confidence, f"{distance:020.6f}:{slot.id}")
        candidates.append((rank, target))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _contains(rect: Rect, x: float, y: float) -> bool:
    return rect.left <= x <= rect.right and rect.top <= y <= rect.bottom


def _distance_to_rect(rect: Rect, x: float, y: float) -> float:
    dx = max(rect.left - x, 0.0, x - rect.right)
    dy = max(rect.top - y, 0.0, y - rect.bottom)
    return hypot(dx, dy)
