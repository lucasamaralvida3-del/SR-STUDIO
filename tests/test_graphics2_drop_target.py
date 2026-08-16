from __future__ import annotations

from srstudio.graphics2.drop_target import find_drop_target, smart_slot_bounds
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform


def _slot(page, slot_id: str, x: float, y: float, width: float, height: float, *, confidence: float = 1.0):
    node = GraphicsNode(
        kind=NodeKind.RECT,
        name=slot_id,
        transform=Transform(x=x, y=y, width=width, height=height),
    )
    page.add_node(node)
    slot = SmartSlot(
        id=slot_id,
        page_id=page.id,
        node_by_role={"name": node.id},
        confidence=confidence,
    )
    page.slots[slot.id] = slot
    return slot, node


def test_drop_target_uses_slot_node_bounds():
    page = GraphicsDocument().active_page
    slot, _ = _slot(page, "slot-a", 100, 200, 300, 250)

    bounds = smart_slot_bounds(page, slot)
    target = find_drop_target(page, 250, 300)

    assert bounds is not None
    assert (bounds.x, bounds.y, bounds.width, bounds.height) == (100, 200, 300, 250)
    assert target is not None
    assert target.slot_id == "slot-a"
    assert target.inside is True
    assert target.distance == 0


def test_overlapping_drop_prefers_smaller_more_specific_card():
    page = GraphicsDocument().active_page
    _slot(page, "large", 0, 0, 600, 600, confidence=1.0)
    _slot(page, "small", 100, 100, 180, 160, confidence=0.8)

    target = find_drop_target(page, 150, 150)

    assert target is not None
    assert target.slot_id == "small"


def test_drop_magnet_accepts_near_edge_but_not_distant_point():
    page = GraphicsDocument().active_page
    _slot(page, "slot", 100, 100, 100, 100)

    assert find_drop_target(page, 205, 150) is None
    near = find_drop_target(page, 205, 150, magnet_distance=8)
    far = find_drop_target(page, 240, 150, magnet_distance=8)

    assert near is not None and near.slot_id == "slot" and near.inside is False
    assert round(near.distance, 3) == 5.0
    assert far is None


def test_locked_slot_never_receives_drop():
    page = GraphicsDocument().active_page
    slot, _ = _slot(page, "locked", 0, 0, 200, 200)
    slot.locked = True

    assert find_drop_target(page, 50, 50, magnet_distance=50) is None
