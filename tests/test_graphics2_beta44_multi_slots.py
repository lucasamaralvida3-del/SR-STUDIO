from __future__ import annotations

import json

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import bind_product_to_item_slot, create_item_slot
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession


def make_session():
    document = GraphicsDocument(name="Beta 44")
    document.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(document)


@pytest.mark.parametrize("count", [5, 6])
def test_multi_strip_has_independent_slots_and_one_movable_parent(count):
    session = make_session()
    data = create_multi_item_strip(session, count=count)
    page = session.page
    group = page.node(data["root_node_id"])
    assert group is not None and group.metadata["multi_slot_beta44"]
    assert len(data["slot_ids"]) == count
    assert len({page.slots[sid].metadata["root_node_id"] for sid in data["slot_ids"]}) == count
    for index, sid in enumerate(data["slot_ids"]):
        slot = page.slots[sid]
        assert slot.metadata["multi_index"] == index
        assert page.node(slot.metadata["root_node_id"]).parent_id == group.id
        assert BindingRole.IMAGE.value in slot.node_by_role
        assert BindingRole.RETAIL_PRICE.value in slot.node_by_role
    before = page.node(page.slots[data["slot_ids"][0]].metadata["root_node_id"]).transform.x
    session.selection = {group.id}
    session.move_selected(12, 0)
    after = page.node(page.slots[data["slot_ids"][0]].metadata["root_node_id"]).transform.x
    assert after == pytest.approx(before + 12)


def test_multi_cells_bind_distinct_products_and_switch_prices():
    session = make_session()
    router = ItemSlotCommandRouter(session)
    data = create_multi_item_strip(session, count=5)
    one, two = data["slot_ids"][:2]
    assert bind_product_to_item_slot(session, one, {
        "id": "SKU-A", "name": "Produto A", "price": "8,99",
    })
    assert bind_product_to_item_slot(session, two, {
        "id": "SKU-B", "name": "Produto B", "price": "19,99",
        "club_price": "16,99",
    })
    page = session.page
    assert page.slots[one].product_id == "SKU-A"
    assert page.slots[two].product_id == "SKU-B"
    first_extra = page.node(page.slots[one].node_by_role[BindingRole.RETAIL_PRICE.value])
    second_extra = page.node(page.slots[two].node_by_role[BindingRole.RETAIL_PRICE.value])
    assert not first_extra.visible
    assert second_extra.visible
    assert "19,99" in second_extra.text
    out = router.dispatch({"name": "set_item_price_mode", "multi_root_id": data["root_node_id"], "mode": "one"})
    assert out.ok
    assert not second_extra.visible
    restored = GraphicsDocument.from_dict(session.document.to_dict())
    assert len(restored.active_page.slots) == 5
    assert restored.active_page.slots[one].product_id == "SKU-A"


def test_single_promotional_slot_supports_two_prices_and_optional_limit():
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    assert bind_product_to_item_slot(session, slot.id, {
        "id": "OIL", "name": "Óleo ABC", "price": "8,99",
        "club_price": "7,99", "cpf_limit": 20,
    })
    page = session.page
    assert page.node(slot.node_by_role[BindingRole.RETAIL_PRICE.value]).visible
    assert page.node(slot.node_by_role[BindingRole.LIMIT.value]).visible


@pytest.mark.parametrize("mode,count", [("individual",1), ("six",6),("seven",7),("eleven",11),("auto",5)])
def test_apply_promotional_layout_creates_editable_boundaries(mode, count):
    session = make_session()
    router = ItemSlotCommandRouter(session)
    cmd = {"name": "apply_promotion_layout", "mode": mode}
    if mode == "auto":
        cmd["count"] = count
    out = router.dispatch(cmd)
    assert out.ok, out.message
    assert len(out.payload["slot_ids"]) == count
    assert len(session.page.slots) == count
    for sid in out.payload["slot_ids"]:
        slot = session.page.slots[sid]
        root = session.page.node(slot.metadata["root_node_id"])
        assert root.transform.y >= .24 * session.page.height
        assert root.transform.y + root.transform.height <= session.page.height


def test_router_multi_command_and_payload_contract():
    router = ItemSlotCommandRouter(make_session())
    result = json.loads(router.dispatch_json(
        json.dumps({"name": "add_multi_item_slot", "count": 6, "price_mode": "two"}),
        include_scene_payload=False,
    ))
    assert result["ok"]
    assert len(result["payload"]["slot_ids"]) == 6
