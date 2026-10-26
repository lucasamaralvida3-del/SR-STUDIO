"""Beta50 regression checks for the *actual* user screenshots and PowerPoints.

Source refs: individual(2).pptx, INDIVIDUAL DOIS PRECOS.pptx,
MULTI SLOTS DOIS PR~ÇOS.pptx, image(20261026-173846).png.
"""
from pathlib import Path

import pytest
from PIL import Image

from srstudio.graphics2.item_slots import (
    create_item_slot, bind_product_to_item_slot, duplicate_item_slot,
    refresh_all_item_slots, set_reference_price_mode,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.two_price_reference import TWO_PRICE_GEOMETRY


def session():
    document = GraphicsDocument(name="Beta50 fidelity")
    document.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(document)


def sample(tmp_path):
    path = tmp_path / "one-product.png"
    Image.new("RGB", (100, 120), "#45A1C3").save(path)
    return {"id": "123", "name": "ABS SEMPRE LIVRE 8X1 P7 L8",
            "price": "3,99", "club_price": "3,89", "image_path": str(path)}


def _overlap(a, b):
    x = max(0.0, min(a.right, b.right) - max(a.x, b.x))
    y = max(0.0, min(a.bottom, b.bottom) - max(a.y, b.y))
    return x * y


def test_individual_backdrop_exists_empty_and_persists_across_modes(tmp_path):
    s = session()
    slot = create_item_slot(s, "individual-beta44")
    page = s.page
    backdrop = page.node(slot.metadata["name_backdrop_node_id"])
    title = page.node(slot.node_by_role[BindingRole.NAME.value])
    image = page.node(slot.node_by_role[BindingRole.IMAGE.value])
    assert backdrop is not None
    assert backdrop.style["fill"] == "#FFFFFF"
    assert backdrop.z_index < title.z_index
    assert backdrop.z_index > image.z_index
    assert backdrop.parent_id == slot.metadata["root_node_id"]
    assert _overlap(title.rect, backdrop.rect) > 0

    assert bind_product_to_item_slot(s, slot.id, sample(tmp_path))
    title = page.node(slot.node_by_role[BindingRole.NAME.value])
    backdrop = page.node(slot.metadata["name_backdrop_node_id"])
    assert title.rect.x >= backdrop.rect.x
    assert title.rect.right <= backdrop.rect.right + .01
    assert title.rect.y >= backdrop.rect.y
    assert title.rect.bottom <= backdrop.rect.bottom + .01
    assert slot.metadata["two_price_reference_revision"] == 51
    assert set_reference_price_mode(s, [slot.id], "one") == [slot.id]
    assert page.node(slot.metadata["name_backdrop_node_id"]).visible
    assert set_reference_price_mode(s, [slot.id], "two") == [slot.id]
    assert page.node(slot.metadata["name_backdrop_node_id"]).visible
    assert slot.product_id == "123"


def test_individual_promotion_badge_is_only_slightly_larger_than_beta49(tmp_path):
    s = session()
    slot = create_item_slot(s, "individual-beta44")
    bind_product_to_item_slot(s, slot.id, sample(tmp_path))
    badge = s.page.node(slot.metadata["two_price_badge_node_id"]).rect
    root = s.page.node(slot.metadata["root_node_id"]).rect
    width_fraction = badge.width / root.width
    height_fraction = badge.height / root.height
    assert .145 < width_fraction < .18
    assert .094 < height_fraction < .12
    assert badge.right <= root.right + .01
    assert badge.bottom <= root.bottom + .01
    assert s.page.node(slot.metadata["club_label_node_id"]).text == "NO CLUBE SR"


@pytest.mark.parametrize("count", (5, 6))
def test_multi_badges_smaller_and_legends_do_not_overlap_price_digits(tmp_path, count):
    s = session()
    strip = create_multi_item_strip(s, count=count, price_mode="two")
    parent = s.page.node(strip["root_node_id"])
    for slot_id in strip["slot_ids"]:
        slot = s.page.slots[slot_id]
        product = sample(tmp_path)
        product["id"] = "PROD-" + slot_id
        bind_product_to_item_slot(s, slot_id, product)
        root = s.page.node(slot.metadata["root_node_id"])
        badge = s.page.node(slot.metadata["two_price_badge_node_id"])
        assert .31 <= badge.rect.width / root.rect.width <= .355
        assert .18 <= badge.rect.height / root.rect.height <= .205
        promo = s.page.node(slot.metadata["promotion_label_node_id"])
        secondary = s.page.node(slot.node_by_role[BindingRole.RETAIL_PRICE.value])
        club = s.page.node(slot.metadata["club_label_node_id"])
        integer = s.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value])
        cents = s.page.node(slot.node_by_role[BindingRole.PRICE_CENTS.value])
        unit = s.page.node(slot.node_by_role[BindingRole.UNIT.value])
        assert promo.text == "NA PROMOÇÃO" and promo.visible
        assert club.text == "NO CLUBE SR" and club.visible
        assert secondary.visible and secondary.text == "R$ 3,99"
        assert club.style["nowrap"] is True
        assert club.style["wrap"] is False
        assert _overlap(club.rect, cents.rect) == 0
        assert _overlap(club.rect, unit.rect) == 0
        assert _overlap(club.rect, integer.rect) == 0
        assert badge.rect.right <= root.rect.right
        assert promo.rect.right <= root.rect.right
    assert len(strip["slot_ids"]) == count
    assert len({s.page.slots[sid].product_id for sid in strip["slot_ids"]}) == count
    assert sum(s.page.node(node_id).name == "Faixa azul contínua"
               for node_id in parent.children) == 1


def test_duplicates_have_own_white_panel_and_badge(tmp_path):
    s = session()
    first = create_item_slot(s, "individual-beta44")
    bind_product_to_item_slot(s, first.id, sample(tmp_path))
    other = duplicate_item_slot(s, first.id)
    assert first.metadata["name_backdrop_node_id"] != other.metadata["name_backdrop_node_id"]
    assert first.metadata["two_price_badge_node_id"] != other.metadata["two_price_badge_node_id"]
    assert s.page.node(other.metadata["name_backdrop_node_id"]).parent_id == other.metadata["root_node_id"]
    assert s.page.node(other.metadata["name_backdrop_node_id"]).visible
    assert not s.page.node(other.metadata["two_price_badge_node_id"]).visible
    assert not other.product_id


def test_saved_beta49_scenes_recover_missing_panel_without_new_slots(tmp_path):
    s = session()
    slot = create_item_slot(s, "individual-beta44")
    bind_product_to_item_slot(s, slot.id, sample(tmp_path))
    old_id = slot.id
    old_price = slot.metadata["original_product_snapshot"]
    backdrop_id = slot.metadata.pop("name_backdrop_node_id")
    s.page.remove_node(backdrop_id)
    slot.metadata["two_price_reference_revision"] = 49
    serialized = GraphicsDocument.from_dict(s.document.to_dict())
    refresh_all_item_slots(serialized)
    restored = serialized.active_page.slots[old_id]
    assert restored.product_id == "123"
    assert restored.metadata["original_product_snapshot"] == old_price
    new_id = restored.metadata["name_backdrop_node_id"]
    assert new_id != backdrop_id
    assert serialized.active_page.node(new_id) is not None
    before = len(serialized.active_page.nodes)
    refresh_all_item_slots(serialized)
    assert len(serialized.active_page.nodes) == before


def test_editor_labels_do_not_cover_all_multi_slots_when_edit_mode_enabled():
    qml = (Path(__file__).parents[1] / "src" / "srstudio"
           / "graphics2" / "qml" / "GraphicsEditor.qml").read_text(encoding="utf-8")
    assert "visible: isSelectedSlot || isHoveredSlot || isDropTarget" in qml
