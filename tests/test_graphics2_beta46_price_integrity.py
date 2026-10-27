from __future__ import annotations

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import (
    bind_product_to_item_slot, create_item_slot, duplicate_item_slot,
    set_reference_price_mode,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession


def make_session() -> GraphicsSession:
    doc = GraphicsDocument(name="Beta46 price regression")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


def read(session: GraphicsSession, sid: str):
    page = session.page
    slot = page.slots[sid]
    price = page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).text
    cents = page.node(slot.node_by_role[BindingRole.PRICE_CENTS.value]).text
    badge = page.node(slot.node_by_role[BindingRole.RETAIL_PRICE.value])
    club = page.node(slot.metadata["club_label_node_id"])
    promotion = page.node(slot.metadata["promotion_label_node_id"])
    # RETAIL_PRICE remains editable in the product data model, but its single
    # text render is replaced with the visible 3-part promotional typography.
    assert not badge.visible
    pieces = slot.metadata.get("promotion_amount_nodes") or {}
    displayed = bool(pieces) and all(page.node(nid).visible for nid in pieces.values())
    return price, cents, badge.text, displayed, club.visible, promotion.visible


@pytest.mark.parametrize("preset", ["individual-beta44", "multi-cell-beta44"])
def test_switching_single_to_club_and_back_preserves_original_retail(preset):
    session = make_session()
    slot = create_item_slot(session, preset)
    retail = {"id": "OIL", "name": "Oleo 900 ML", "price": "8,99", "club_price": "7,49"}
    assert bind_product_to_item_slot(session, slot.id, retail)
    before = read(session, slot.id)
    assert before[0] == "7"
    assert before[2] == "R$ 8,99" and before[3]

    assert set_reference_price_mode(session, [slot.id], "one") == [slot.id]
    single = read(session, slot.id)
    assert single[0] == "8"
    assert single[2] == "" and not single[3] and not single[4] and single[5]

    assert set_reference_price_mode(session, [slot.id], "two") == [slot.id]
    assert read(session, slot.id) == before

    assert set_reference_price_mode(session, [slot.id], "auto") == [slot.id]
    assert read(session, slot.id) == before
    assert session.page.slots[slot.id].metadata["original_product_snapshot"] == retail
    assert session.page.slots[slot.id].product_id == "OIL"


def test_auto_is_one_when_prices_match():
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, {
        "id": "A", "name": "Produto A", "price": "9,99", "club_price": "9,99"
    })
    assert read(session, slot.id)[0] == "9"
    assert read(session, slot.id)[3:] == (False, False, True)
    set_reference_price_mode(session, [slot.id], "two")
    assert read(session, slot.id)[3]
    set_reference_price_mode(session, [slot.id], "auto")
    assert read(session, slot.id)[3:] == (False, False, True)


@pytest.mark.parametrize("count", [5, 6])
def test_multi_price_mode_is_one_undo_step_for_all_cells(count):
    session = make_session()
    multi = create_multi_item_strip(session, count=count)
    for index, sid in enumerate(multi["slot_ids"]):
        bind_product_to_item_slot(session, sid, {
            "id": f"SKU-{index}", "name": f"Produto {index}",
            "price": "12,99", "club_price": "10,99",
        })
    router = ItemSlotCommandRouter(session)
    result = router.dispatch({
        "name": "set_item_price_mode", "multi_root_id": multi["root_node_id"], "mode": "one"
    })
    assert result.ok
    assert all(read(session, sid)[0] == "12" for sid in multi["slot_ids"])
    assert session.undo()
    assert all(read(session, sid)[0] == "10" for sid in multi["slot_ids"])
    assert session.redo()
    assert all(read(session, sid)[0] == "12" for sid in multi["slot_ids"])


def test_older_beta45_snapshot_can_recover_retail_mode():
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, {
        "id": "OLD", "name": "Shampoo", "price": "10,99", "club_price": "8,99"
    })
    slot.metadata.pop("original_product_snapshot", None)
    set_reference_price_mode(session, [slot.id], "one")
    assert read(session, slot.id)[0] == "10"
    set_reference_price_mode(session, [slot.id], "auto")
    assert read(session, slot.id)[0] == "8"


def test_duplicate_of_bound_slot_is_clean_and_source_untouched():
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, {
        "id": "SKU", "name": "Produto", "price": "19,99", "club_price": "15,99",
        "cpf_limit": 3, "image_path": "test-picture.png",
    })
    source_state = read(session, slot.id)
    clone = duplicate_item_slot(session, slot.id)
    assert clone.product_id == ""
    assert clone.metadata["original_product_snapshot"] == {}
    assert clone.metadata["price_mode"] == "auto"
    assert clone.metadata["price_variant"] == "one"
    assert session.page.node(clone.node_by_role[BindingRole.RETAIL_PRICE.value]).visible is False
    assert session.page.node(clone.node_by_role[BindingRole.LIMIT.value]).visible is False
    assert session.page.node(clone.node_by_role[BindingRole.IMAGE.value]).visible is False
    assert read(session, clone.id)[3:] == (False, False, True)
    assert read(session, slot.id) == source_state


def test_restore_after_save_and_reopen_preserves_retail_mode():
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, {
        "id": "R", "name": "Rice", "price": "29,90", "club_price": "24,90"
    })
    set_reference_price_mode(session, [slot.id], "one")
    saved = session.document.to_dict()
    reopened = GraphicsSession(GraphicsDocument.from_dict(saved))
    set_reference_price_mode(reopened, [slot.id], "auto")
    assert read(reopened, slot.id)[0] == "24"
    assert reopened.page.slots[slot.id].product_id == "R"


@pytest.mark.parametrize("preset", ["individual-beta44", "multi-cell-beta44"])
def test_replacing_product_does_not_reuse_previous_sku_picture(preset):
    session = make_session()
    slot = create_item_slot(session, preset)
    bind_product_to_item_slot(session, slot.id, {
        "id": "OLD", "name": "Produto antigo", "price": "8,99",
        "image_path": "old-sku-photo.png",
    })
    image = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    assert image.metadata["bound_image_source"] == "old-sku-photo.png"
    assert image.visible

    # Price-only edit of the SAME product keeps its picture.
    bind_product_to_item_slot(session, slot.id, {
        "id": "OLD", "name": "Produto antigo", "price": "9,99"
    })
    assert image.metadata["bound_image_source"] == "old-sku-photo.png"
    assert image.visible

    # Switching to another SKU with no image must not show old SKU's photo.
    bind_product_to_item_slot(session, slot.id, {
        "id": "NEW", "name": "Produto novo", "price": "6,99"
    })
    assert "bound_image_source" not in image.metadata
    assert image.asset_id == ""
    assert image.metadata["placeholder"]
    assert not image.visible
    assert session.page.slots[slot.id].product_id == "NEW"

    # A later product-image update restores the new SKU's picture.
    bind_product_to_item_slot(session, slot.id, {
        "id": "NEW", "name": "Produto novo", "price": "6,99",
        "image_path": "new-sku-photo.png",
    })
    assert image.visible
    assert image.metadata["bound_image_source"] == "new-sku-photo.png"
    assert not image.metadata["placeholder"]
