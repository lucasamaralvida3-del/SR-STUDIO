from __future__ import annotations

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.slot_fill_plan import apply_slot_fill_plan, plan_smart_slot_fill


def _session():
    document = GraphicsDocument(name="Preenchimento")
    page = document.active_page
    slots = []
    specs = [
        (20, 20, 0.95, False, ""),
        (300, 20, 0.40, False, ""),
        (20, 300, 0.98, True, ""),
        (300, 300, 0.90, False, "produto-antigo"),
        (20, 600, 0.88, False, ""),
    ]
    for index, (x, y, confidence, locked, product_id) in enumerate(specs):
        name = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"Nome {index}",
            text="",
            transform=Transform(x=x, y=y, width=200, height=40),
        )
        page.add_node(name)
        slot = SmartSlot(
            name=f"Slot {index}",
            page_id=page.id,
            node_by_role={BindingRole.NAME.value: name.id},
            confidence=confidence,
            locked=locked,
            product_id=product_id,
        )
        page.slots[slot.id] = slot
        slots.append((slot, name))
    return GraphicsSession(document), slots


def _products():
    return [
        {"id": "p1", "display_name": "ACÉM"},
        {"id": "p2", "display_name": "LINGUIÇA"},
        {"id": "p3", "display_name": "COSTELA"},
    ]


def test_slot_fill_plan_is_conservative_and_non_mutating():
    session, slots = _session()
    before = session.document.to_dict()

    plan = plan_smart_slot_fill(session, _products(), min_confidence=0.72)

    assert session.document.to_dict() == before
    assert [item.slot_id for item in plan.assignments] == [slots[0][0].id, slots[4][0].id]
    reasons = {item.slot_id: item.reason for item in plan.skipped_slots}
    assert reasons[slots[1][0].id] == "low_confidence"
    assert reasons[slots[2][0].id] == "locked"
    assert reasons[slots[3][0].id] == "already_populated"
    assert plan.unassigned_product_indexes == (2,)


def test_apply_slot_fill_plan_populates_only_reviewed_slots():
    session, slots = _session()
    products = _products()
    plan = plan_smart_slot_fill(session, products, min_confidence=0.72)

    report = apply_slot_fill_plan(session, plan, products)

    assert report.changed
    assert report.applied == (slots[0][0].id, slots[4][0].id)
    assert report.rejected == ()
    assert slots[0][0].product_id == "p1"
    assert slots[4][0].product_id == "p2"
    assert session.page.node(slots[0][1].id).text == "ACÉM"
    assert session.page.node(slots[4][1].id).text == "LINGUIÇA"
    assert slots[1][0].product_id == ""
    assert slots[3][0].product_id == "produto-antigo"


def test_apply_slot_fill_plan_rejects_stale_slot_state_instead_of_overwriting():
    session, slots = _session()
    products = _products()
    plan = plan_smart_slot_fill(session, products, min_confidence=0.72)

    slots[0][0].product_id = "mudou-depois-do-plano"
    report = apply_slot_fill_plan(session, plan, products)

    assert slots[0][0].id not in report.applied
    assert (slots[0][0].id, "slot_state_changed") in report.rejected
    assert session.page.node(slots[0][1].id).text == ""


def test_overwrite_plan_can_include_populated_high_confidence_slot_but_not_locked_or_low_confidence():
    session, slots = _session()
    plan = plan_smart_slot_fill(session, _products(), overwrite=True, min_confidence=0.72)

    planned = [item.slot_id for item in plan.assignments]
    assert slots[0][0].id in planned
    assert slots[3][0].id in planned
    assert slots[1][0].id not in planned
    assert slots[2][0].id not in planned
