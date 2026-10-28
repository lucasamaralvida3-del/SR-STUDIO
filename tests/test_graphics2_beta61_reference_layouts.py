"""Beta61: photograph-faithful layout topology and flexible canonical Multi 2–8."""
from __future__ import annotations

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import bind_product_to_item_slot
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip, set_multi_item_count
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.promotion_layouts import plan_promotion
from srstudio.graphics2.promotion_composition import apply_slot_composition


def session():
    doc = GraphicsDocument(name="Imagem de referência Terça Verde")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


@pytest.mark.parametrize("mode,expected", [
    ("seven", ["individual"] + ["single"] * 2 + ["multi"] * 4),
    ("eleven", ["single"] * 6 + ["multi"] * 5),
    ("nine", ["single"] * 4 + ["multi"] * 5),
    ("six", ["single"] * 6),
])
def test_reference_template_is_exact_canonical_topology(mode, expected):
    plan = plan_promotion(mode)
    assert [p.kind for p in plan.placements] == expected
    s = session()
    result = apply_slot_composition(s, plan, reuse_existing=True)
    assert len(result.slot_ids) == len(expected)
    assert len(s.page.slots) == len(expected)
    for role, slot_id in zip(expected, result.slot_ids):
        slot = s.page.slots[slot_id]
        if role == "single":
            assert slot.metadata.get("limpeza_blue_profile") == "limpeza-blue-v1"
        elif role == "individual":
            assert slot.metadata["preset_id"] == "individual-beta44"
        else:
            assert slot.metadata["preset_id"] == "multi-cell-beta44"
        assert slot.node_by_role[BindingRole.IMAGE.value]
        assert slot.node_by_role[BindingRole.PRICE_REAIS.value]
    groups = [n for n in s.page.nodes.values() if n.metadata.get("multi_slot_beta44")]
    if "multi" in expected:
        assert len(groups) == 1
        assert groups[0].metadata["multi_count"] == expected.count("multi")
        assert groups[0].metadata["child_slot_ids"] == list(result.slot_ids[-expected.count("multi"):])
        assert len(result.root_node_ids) == len(expected) - expected.count("multi") + 1
    else:
        assert not groups
    for position, sid in zip(plan.placements, result.slot_ids):
        root_id = s.page.slots[sid].metadata["root_node_id"]
        root = s.page.node(root_id)
        assert 0 <= root.rect.x and root.rect.right <= s.page.width + .001
        assert root.rect.y >= plan.logo_reserved * s.page.height
        assert root.rect.bottom <= s.page.height + .001
        assert position.kind != "multi" or root.parent_id == groups[0].id


@pytest.mark.parametrize("count", range(2, 9))
def test_multi_2_through_8_has_one_real_ribbon_and_independent_cells(count):
    s = session()
    result = create_multi_item_strip(s, count=count)
    root = s.page.node(result["root_node_id"])
    assert root.metadata["multi_count"] == count
    assert len(root.metadata["child_slot_ids"]) == count
    descendants = [s.page.node(x) for x in s.page.descendants(root.id)]
    assert sum(n.name == "Faixa azul contínua" for n in descendants) == 1
    assert sum(n.name.startswith("Divisor ") for n in descendants) == count - 1
    for index, sid in enumerate(result["slot_ids"]):
        assert s.page.slots[sid].metadata["multi_index"] == index
        assert s.page.slots[sid].metadata["multi_count"] == count


def test_multi_resize_keeps_existing_products_and_single_shared_ribbon():
    s = session()
    data = create_multi_item_strip(s, count=4)
    original = list(data["slot_ids"])
    for i, sid in enumerate(original):
        assert bind_product_to_item_slot(s, sid, {
            "id": f"EAN-{i}", "name": "MAÇÃ GALA 1KG",
            "price": f"{i+2},99", "unit": "KG"})
    grow = set_multi_item_count(s, data["root_node_id"], 8)
    assert len(grow["slot_ids"]) == 8
    assert grow["slot_ids"][:4] == original
    assert all(s.page.slots[sid].product_id == f"EAN-{i}"
               for i, sid in enumerate(original))
    for sid in grow["slot_ids"][4:]:
        assert not s.page.slots[sid].product_id
    shrink = set_multi_item_count(s, data["root_node_id"], 4)
    assert shrink["slot_ids"] == original
    assert len(s.page.slots) == 4
    assert len(s.page.node(data["root_node_id"]).metadata["child_slot_ids"]) == 4


def test_multi_never_discards_a_filled_product_when_shrunk():
    s = session()
    data = create_multi_item_strip(s, count=5)
    last = data["slot_ids"][-1]
    assert bind_product_to_item_slot(s, last, {
        "id": "SKU-FIVE", "name": "MORANGO BANDEJA", "price": "6,67"})
    before = s.document.to_dict()
    with pytest.raises(ValueError, match="produtos nos espaços"):
        set_multi_item_count(s, data["root_node_id"], 4)
    assert s.document.to_dict() == before


@pytest.mark.parametrize("count", [1, 9, 0, -1])
def test_multi_rejects_invalid_counts(count):
    s = session()
    with pytest.raises(ValueError, match="2 a 8"):
        create_multi_item_strip(s, count=count)


def test_seven_product_layout_reuses_a_filled_multi_4_without_splitting():
    s = session()
    multi = create_multi_item_strip(s, count=4)
    for i, sid in enumerate(multi["slot_ids"]):
        bind_product_to_item_slot(s, sid, {
            "id": f"MULTI-{i}", "name": "FRUTA 1KG", "price": f"{i+5},99"})
    r = ItemSlotCommandRouter(s).dispatch({
        "name": "apply_promotion_layout", "mode": "seven", "reuse_existing": True})
    assert r.ok, r.message
    assert multi["root_node_id"] in r.payload["root_node_ids"]
    assert set(multi["slot_ids"]).issubset(set(r.payload["reused_slot_ids"]))


def test_legacy_multi_5_shrinks_only_if_last_cell_is_empty():
    s = session()
    multi = create_multi_item_strip(s, count=5)
    for sid in multi["slot_ids"][:4]:
        bind_product_to_item_slot(s, sid, {
            "id": sid, "name": "FRUTA 1KG", "price": "5,99"})
    r = ItemSlotCommandRouter(s).dispatch({
        "name": "apply_promotion_layout", "mode": "seven", "reuse_existing": True})
    assert r.ok, r.message
    assert s.page.node(multi["root_node_id"]).metadata["multi_count"] == 4
    assert not any(sid in s.page.slots for sid in multi["slot_ids"][4:])


def test_multi_count_command_validates_user_input_without_mutation():
    s = session()
    r = ItemSlotCommandRouter(s)
    multi = r.dispatch({"name": "add_multi_item_slot", "count": 2})
    assert multi.ok
    root_id = multi.payload["root_node_id"]
    changed = r.dispatch({"name": "set_multi_item_count", "root_node_id": root_id,
                          "count": 8})
    assert changed.ok
    assert len(changed.payload["slot_ids"]) == 8
    original = s.document.to_dict()
    bad = r.dispatch({"name": "set_multi_item_count", "root_node_id": root_id,
                      "count": 9})
    assert not bad.ok
    assert s.document.to_dict() == original


def test_multi_variations_and_layout_labels_are_exposed_in_editor():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src/srstudio/graphics2"
    qml = (root / "qml/GraphicsEditor.qml").read_text("utf-8")
    assert 'from: 2; to: 8; value: 5; editable: true' in qml
    assert 'name":"set_multi_item_count"' in qml
    assert 'name":"apply_promotion_layout"' in qml
    assert '7 · Individual + 2 Únicos + Multi-4' in qml
    assert '11 · 6 Únicos + Multi-5' in qml


def test_multi_resize_is_idempotent_at_same_size():
    s = session()
    multi = create_multi_item_strip(s, count=8, price_mode="two")
    before = s.document.to_dict()
    updated = set_multi_item_count(s, multi["root_node_id"], 8)
    assert updated["slot_ids"] == multi["slot_ids"]
    assert s.document.to_dict() == before


def test_multi_cannot_resize_a_non_multi_root():
    s = session()
    with pytest.raises(ValueError, match="faixa Multi real"):
        set_multi_item_count(s, "not-a-real-root", 3)
