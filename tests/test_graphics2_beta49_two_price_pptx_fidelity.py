"""Geometry and persistence contracts from the user's actual two-price PPTX.

INDIVIDUAL DOIS PRECOS.pptx: mini blue promotion badge at lower-left of
large club plate; simultaneous 'NA PROMOÇÃO' and 'NO CLUBE SR'.
MULTI SLOTS DOIS PR~ÇOS.pptx: five independent mini badges above one
continuous blue pricing ribbon. Preserve 1-price canvas and saved product IDs.
"""
from __future__ import annotations

import pytest

from srstudio.graphics2.item_slots import (
    bind_product_to_item_slot, create_item_slot, duplicate_item_slot,
    set_reference_price_mode, refresh_all_item_slots,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.two_price_reference import TWO_PRICE_GEOMETRY


def make_session():
    doc = GraphicsDocument(name="Two-price user PPTX")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


def ratio_bbox(rect, root):
    return ((rect.x - root.x) / root.width,
            (rect.y - root.y) / root.height,
            rect.width / root.width,
            rect.height / root.height)


@pytest.mark.parametrize("preset", ("individual-beta44", "multi-cell-beta44"))
def test_two_price_pptx_has_separate_badge_with_both_labels(preset, tmp_path):
    from PIL import Image
    photo = tmp_path / "product.png"
    Image.new("RGB", (90, 120), "#597FC2").save(photo)
    s = make_session()
    slot = create_item_slot(s, preset)
    root = s.page.node(slot.metadata["root_node_id"])
    one_main = s.page.node(slot.metadata["role_area_nodes"]["price"]).rect
    product = {"id": "789012", "name": "OVO DE GALINHA CARTELA 30UN",
               "price": "24,86", "club_price": "21,49", "unit": "UN",
               "image_path": str(photo)}
    assert bind_product_to_item_slot(s, slot.id, product)
    badge = s.page.node(slot.metadata["two_price_badge_node_id"])
    assert badge is not None and badge.parent_id == root.id and badge.visible
    assert badge.metadata["item_slot_two_price_badge"]
    desired = TWO_PRICE_GEOMETRY[preset]["badge"]
    assert ratio_bbox(badge.rect, root.rect) == pytest.approx(desired, abs=.005)
    assert badge.z_index > 30

    promo = s.page.node(slot.metadata["promotion_label_node_id"])
    club = s.page.node(slot.metadata["club_label_node_id"])
    retail = s.page.node(slot.node_by_role[BindingRole.RETAIL_PRICE.value])
    assert promo.visible and club.visible and retail.visible
    assert promo.text == "NA PROMOÇÃO" and club.text == "NO CLUBE SR"
    assert retail.text == "R$ 24,86"
    assert ratio_bbox(promo.rect, root.rect) == pytest.approx(
        TWO_PRICE_GEOMETRY[preset]["promo_label"], abs=.005)
    assert ratio_bbox(retail.rect, root.rect) == pytest.approx(
        TWO_PRICE_GEOMETRY[preset]["secondary_price"], abs=.005)
    assert ratio_bbox(club.rect, root.rect) == pytest.approx(
        TWO_PRICE_GEOMETRY[preset]["club_label"], abs=.005)
    assert slot.metadata["two_price_reference_revision"] == 49
    assert slot.product_id == "789012"
    if preset == "individual-beta44":
        primary = s.page.node(slot.node_by_role[BindingRole.IMAGE.value])
        repeated = s.page.node(slot.metadata["image_repeat_node_id"])
        assert repeated is not None and not repeated.visible
        assert ratio_bbox(primary.rect, root.rect) == pytest.approx(
            TWO_PRICE_GEOMETRY[preset]["image"], abs=.005)

    assert set_reference_price_mode(s, [slot.id], "one") == [slot.id]
    assert not badge.visible and not club.visible and not retail.visible
    assert promo.visible
    if preset == "individual-beta44":
        assert s.page.node(slot.metadata["image_repeat_node_id"]).visible
    assert slot.product_id == "789012"
    assert s.page.node(slot.metadata["role_area_nodes"]["price"]).rect == one_main
    assert set_reference_price_mode(s, [slot.id], "two") == [slot.id]
    assert badge.visible and club.visible and promo.visible
    assert retail.text == "R$ 24,86"


@pytest.mark.parametrize("count", [5, 6])
def test_multi_pptx_two_price_cells_share_one_ribbon_not_their_badges(count):
    s = make_session()
    multi = create_multi_item_strip(s, count=count, price_mode="two")
    root = s.page.node(multi["root_node_id"])
    ribbon = next(s.page.node(nid) for nid in root.children
                  if s.page.node(nid).name == "Faixa azul contínua")
    assert len(multi["slot_ids"]) == count
    for i, sid in enumerate(multi["slot_ids"]):
        slot = s.page.slots[sid]
        assert bind_product_to_item_slot(s, sid, {
            "id": f"SKU{i}", "name": f"Produto {i}", "price": "22,81",
            "club_price": "21,73",
        })
        badge = s.page.node(slot.metadata["two_price_badge_node_id"])
        assert badge.visible
        assert badge.rect.y < ribbon.rect.y
        assert badge.rect.bottom > ribbon.rect.y
        assert badge.parent_id == slot.metadata["root_node_id"]
        assert s.page.node(slot.metadata["club_label_node_id"]).visible
        assert s.page.node(slot.metadata["promotion_label_node_id"]).visible
    assert sum(s.page.node(nid).name == "Faixa azul contínua"
               for nid in root.children) == 1
    assert len({s.page.slots[sid].product_id for sid in multi["slot_ids"]}) == count


def test_old_saved_two_price_is_upgraded_without_losing_product_or_slot():
    s = make_session()
    slot = create_item_slot(s, "individual-beta44")
    bind_product_to_item_slot(s, slot.id, {
        "id": "OLD-SKU", "name": "ITEM ANTIGO", "price": "9,99",
        "club_price": "8,99",
    })
    identity = slot.id
    original_price = slot.metadata["original_product_snapshot"]
    with s.transaction("Emular arte antiga Beta48"):
        badge_id = slot.metadata.pop("two_price_badge_node_id")
        s.page.remove_node(badge_id)
        slot.metadata.pop("two_price_reference_revision", None)
        slot.metadata["reference_fidelity_revision"] = 47
    restored = GraphicsDocument.from_dict(s.document.to_dict())
    refresh_all_item_slots(restored)
    saved = restored.active_page.slots[identity]
    badge = restored.active_page.node(saved.metadata["two_price_badge_node_id"])
    assert badge.visible
    assert saved.product_id == "OLD-SKU"
    assert saved.metadata["original_product_snapshot"] == original_price
    assert saved.metadata["two_price_reference_revision"] == 49
    before = len(restored.active_page.nodes)
    refresh_all_item_slots(restored)
    assert len(restored.active_page.nodes) == before


def test_duplicate_slot_remaps_two_price_badge_and_clears_secondary_price():
    s = make_session()
    original = create_item_slot(s, "individual-beta44")
    bind_product_to_item_slot(s, original.id, {
        "id": "A", "name": "ARROZ", "price": "24,86", "club_price": "21,49"
    })
    clone = duplicate_item_slot(s, original.id)
    bid = original.metadata["two_price_badge_node_id"]
    clone_badge_id = clone.metadata["two_price_badge_node_id"]
    assert clone_badge_id != bid
    assert not s.page.node(clone_badge_id).visible
    assert not s.page.node(clone.node_by_role[BindingRole.RETAIL_PRICE.value]).visible
    assert not clone.product_id
