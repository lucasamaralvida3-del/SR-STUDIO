"""Beta51: regression for the screenshots of blank products and cramped prices.

Approved SKU-linked images may be reused; never guess another SKU or display
an unapproved historical image. Two-price content boxes must be disjoint.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import create_item_slot, bind_product_to_item_slot, refresh_all_item_slots
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.product_image_library import store_product_image
from srstudio.graphics2.two_price_reference import TWO_PRICE_GEOMETRY


def session():
    doc = GraphicsDocument(name="Visual no-overlap regression")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


def product(sku="CAF-500", **updates):
    item = {"id": sku, "name": "CAFÉ VASCONCELOS 500G EXTRA FORTE",
            "price": "27,66", "club_price": "26,89", "unit": "UN"}
    item.update(updates)
    return item


def overlaps(a, b):
    return (min(a.right, b.right) - max(a.x, b.x) > .01
            and min(a.bottom, b.bottom) - max(a.y, b.y) > .01)


@pytest.mark.parametrize("preset", ("individual-beta44", "multi-cell-beta44"))
def test_two_price_text_never_overlaps_other_values(preset):
    s = session()
    slot = create_item_slot(s, preset)
    assert bind_product_to_item_slot(s, slot.id, product())
    page = s.page
    text_roles = [BindingRole.CURRENCY, BindingRole.PRICE_REAIS,
                  BindingRole.PRICE_CENTS, BindingRole.UNIT]
    price_nodes = [page.node(slot.node_by_role[r.value]) for r in text_roles]
    label = page.node(slot.metadata["club_label_node_id"])
    assert label.text == "NO CLUBE SR" and label.visible
    assert label.style["nowrap"]
    assert label.style["font_size"] >= 8.0
    assert all(not overlaps(a.rect, b.rect) for i, a in enumerate(
        price_nodes + [label]) for b in (price_nodes + [label])[i+1:])
    retail_binding = page.node(slot.node_by_role[BindingRole.RETAIL_PRICE.value])
    assert retail_binding.text == "R$ 27,66" and not retail_binding.visible
    small = [page.node(slot.metadata["promotion_label_node_id"])] + [
        page.node(nid) for nid in slot.metadata["promotion_amount_nodes"].values()]
    assert all(node.visible for node in small)
    assert all(not overlaps(a.rect, b.rect)
               for i, a in enumerate(small) for b in small[i+1:])
    for a in small:
        for b in price_nodes + [label]:
            assert not overlaps(a.rect, b.rect), (a.name, b.name)
    assert slot.metadata["two_price_reference_revision"] == 57


@pytest.mark.parametrize("count", (5, 6))
def test_multi_two_price_names_stay_above_images(count):
    s = session()
    multi = create_multi_item_strip(s, count=count, price_mode="two")
    for sid in multi["slot_ids"]:
        slot = s.page.slots[sid]
        bind_product_to_item_slot(s, sid, product(sku=sid))
        name = s.page.node(slot.node_by_role[BindingRole.NAME.value])
        image = s.page.node(slot.node_by_role[BindingRole.IMAGE.value])
        assert name.rect.bottom < image.rect.y
        assert name.rect.height >= .17 * s.page.node(slot.metadata["root_node_id"]).rect.height


def test_editor_command_uses_specialized_reference_binding_and_exact_sku_image(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    source = tmp_path / "cafe.png"
    Image.new("RGB", (80, 100), "blue").save(source)
    store_product_image("CAF-500", "CAFÉ VASCONCELOS", str(source))
    from srstudio.graphics2.product_image_library import read_product_links
    from srstudio.graphics2.legacy_image_bank_bridge import complete_product_image
    assert "CAF-500" in read_product_links()
    assert Path(complete_product_image(product())["image_path"]).is_file()
    direct = session()
    direct_slot = create_item_slot(direct, "individual-beta44")
    assert bind_product_to_item_slot(direct, direct_slot.id, product())
    direct_photo = direct.page.node(direct_slot.node_by_role[BindingRole.IMAGE.value])
    assert direct_photo.asset_id or direct_photo.metadata.get("bound_image_source"), (
        "Direct ItemSlot binder did not retain the exact-SKU image")
    s = session()
    slot = create_item_slot(s, "individual-beta44")
    s.document.metadata["products"] = [product()]
    from srstudio.graphics2.item_slots import is_manual_item_slot
    assert is_manual_item_slot(slot)
    router = ItemSlotCommandRouter(s)
    assert is_manual_item_slot(s.page.slots[slot.id]), s.page.slots[slot.id].metadata
    result = router.dispatch(
        {"name": "bind_product", "slot_id": slot.id, "product_id": "CAF-500"})
    assert result.ok and result.changed
    assert result.payload and result.payload.get("binding_route") == "manual-item-slot", (
        result.payload, result.message)
    current = s.page.slots[slot.id]
    assert "original_product_snapshot" in current.metadata, (
        "Router did not use manual Smart Slot binder", current.metadata, result.message)
    assert current.metadata["original_product_snapshot"].get("image_path"), (
        "Router did not hydrate stored SKU image",
        current.metadata["original_product_snapshot"], result.message)
    image = s.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    assert image.asset_id or image.metadata.get("bound_image_source")
    assert image.visible
    assert slot.metadata["price_variant"] == "two"
    assert slot.metadata["original_product_snapshot"]["image_linked_by"] == "product_id"
    assert s.page.node(slot.metadata["club_label_node_id"]).visible

    # A different SKU without an approved photo must *not* keep CAF-500's pack.
    s.document.metadata["products"] = [product("OUTRO-123")]
    next_result = ItemSlotCommandRouter(s).dispatch(
        {"name": "bind_product", "slot_id": slot.id, "product_id": "OUTRO-123"})
    assert next_result.ok
    assert "sem foto" in next_result.message.lower()
    assert not image.asset_id and not image.metadata.get("bound_image_source")


def test_original_single_price_preset_remains_editable():
    s = session()
    slot = create_item_slot(s, "multi-cell-beta44")
    bind_product_to_item_slot(s, slot.id, {"id": "111", "name": "DET YPÊ",
                                           "price": "4,99", "unit": "UN"})
    club = s.page.node(slot.metadata["club_label_node_id"])
    assert not club.visible
    assert s.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).text == "4"
    assert s.page.node(slot.node_by_role[BindingRole.PRICE_CENTS.value]).text == ",99"


def test_old_beta50_price_geometry_reflows_without_changing_product():
    s = session()
    slot = create_item_slot(s, "individual-beta44")
    bind_product_to_item_slot(s, slot.id, product())
    slot.metadata["two_price_reference_revision"] = 50
    before = slot.metadata["original_product_snapshot"]
    doc = GraphicsDocument.from_dict(s.document.to_dict())
    refresh_all_item_slots(doc)
    saved = doc.active_page.slots[slot.id]
    assert saved.product_id == "CAF-500"
    assert saved.metadata["two_price_reference_revision"] == 57
    assert saved.metadata["original_product_snapshot"] == before
