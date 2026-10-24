from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.item_slots import (
    bind_product_to_item_slot, create_item_slot, duplicate_item_slot,
    refresh_all_item_slots,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.qt_renderer import qt_renderer_available, render_png


BLUE = "#105594"


def session():
    doc = GraphicsDocument(name="Reference fidelidade")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


def get_decor(page, root_id, name):
    found = [page.node(n) for n in page.descendants(root_id)
             if page.node(n) and page.node(n).name == name]
    assert len(found) == 1, (name, found)
    return found[0]


def test_individual_is_reference_art_not_gray_ui_card():
    s = session()
    slot = create_item_slot(s, "individual-beta44", x=150, y=180)
    page = s.page
    root = page.node(slot.metadata["root_node_id"])
    background = get_decor(page, root.id, "ItemSlot Background")
    blue = get_decor(page, root.id, "PRICE BACKGROUND")
    assert background.style["fill"] == "#FFFFFF"
    assert background.style["stroke_width"] == 0
    assert blue.style["fill"] == BLUE
    assert blue.style["radius_ratio"] >= .1
    assert background.z_index < blue.z_index
    assert blue.z_index < page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).z_index
    assert not any(page.node(n).metadata.get("item_slot_image_backplate")
                   and page.node(n).visible for n in page.descendants(root.id))
    name = page.node(slot.node_by_role[BindingRole.NAME.value])
    assert name.style["color"] == BLUE
    assert name.rect.x > root.rect.x + .5 * root.rect.width
    assert slot.metadata["promotion_label_node_id"]


@pytest.mark.parametrize("count", [5, 6])
def test_multi_strips_match_ppt_structure(count):
    s = session()
    result = create_multi_item_strip(s, count=count, x=50, y=550)
    p = s.page
    group = p.node(result["root_node_id"])
    paper = get_decor(p, group.id, "Fundo branco da faixa")
    ribbon = get_decor(p, group.id, "Faixa azul contínua")
    assert paper.style["fill"] == "#FFFFFF"
    assert paper.z_index < ribbon.z_index
    assert ribbon.style["fill"] == BLUE
    assert ribbon.style["radius_ratio"] >= .25
    assert ribbon.rect.x == pytest.approx(group.rect.x)
    assert ribbon.rect.width == pytest.approx(group.rect.width)
    assert ribbon.rect.y == pytest.approx(group.rect.y + .77 * group.rect.height)
    roots = [p.node(p.slots[sid].metadata["root_node_id"]) for sid in result["slot_ids"]]
    assert all(r.rect.width == pytest.approx(group.rect.width / count) for r in roots)
    assert all(r.rect.right <= group.rect.right + 1e-5 for r in roots)
    assert all(p.node(p.slots[sid].node_by_role[BindingRole.NAME.value]).style["color"] == BLUE
               for sid in result["slot_ids"])
    assert all(not any(p.node(n).metadata.get("item_slot_image_backplate")
                           and p.node(n).visible for n in p.descendants(r.id)) for r in roots)


def test_promotion_modes_never_show_promo_and_club_label_together():
    s = session()
    a = create_item_slot(s, "individual-beta44")
    p = s.page
    promo = p.node(a.metadata["promotion_label_node_id"])
    club = p.node(a.metadata["club_label_node_id"])
    extra = p.node(a.node_by_role[BindingRole.RETAIL_PRICE.value])
    assert promo.visible and not club.visible and not extra.visible
    assert bind_product_to_item_slot(s, a.id, {
        "id": "item", "name": "OLEO ABC PET 900ML SOJA", "price": "7,21",
        "club_price": "6,39",
    })
    assert extra.visible and club.visible and not promo.visible
    assert bind_product_to_item_slot(s, a.id, {
        "id": "item", "name": "OLEO ABC PET 900ML SOJA", "price": "7,21",
    })
    assert promo.visible and not club.visible and not extra.visible


def test_saved_beta44_slots_upgrade_without_losing_product():
    s = session()
    multi = create_multi_item_strip(s, count=5)
    individual = create_item_slot(s, "individual-beta44")
    bound = multi["slot_ids"][0]
    assert bind_product_to_item_slot(s, bound, {"id": "SKU-11", "name": "Shampoo", "price": "21,03"})
    page = s.page
    for sid in multi["slot_ids"] + [individual.id]:
        sl = page.slots[sid]
        sl.metadata.pop("reference_fidelity_revision", None)
        page.node(sl.metadata["root_node_id"]).metadata.pop("reference_fidelity_revision", None)
        promo_id = sl.metadata.pop("promotion_label_node_id", None)
        if promo_id:
            page.remove_node(promo_id)
    root = page.node(multi["root_node_id"])
    root.metadata.pop("reference_fidelity_revision", None)
    # Simulate archived previous-generation white input borders.
    sl = page.slots[individual.id]
    for nid in sl.metadata["decorative_nodes"]:
        node = page.node(nid)
        if node and node.metadata.get("item_slot_price_background"):
            node.style["fill"] = "#265398"
    page_before = page.id
    product_before = page.slots[bound].product_id
    refresh_all_item_slots(s.document)
    assert page.id == page_before
    assert page.slots[bound].product_id == product_before
    assert page.node(page.slots[bound].metadata["root_node_id"]) is not None
    assert page.node(page.slots[individual.id].metadata["promotion_label_node_id"]) is not None
    assert get_decor(page, root.id, "Faixa azul contínua").style["fill"] == BLUE
    data = s.document.to_dict()
    restored = GraphicsDocument.from_dict(data)
    assert restored.active_page.slots[bound].product_id == "SKU-11"
    refresh_all_item_slots(restored)  # idempotent
    assert len(restored.active_page.slots) == 6


def test_duplicate_relinks_promotional_labels():
    s = session()
    original = create_item_slot(s, "individual-beta44")
    clone = duplicate_item_slot(s, original.id)
    assert original.metadata["promotion_label_node_id"] != clone.metadata["promotion_label_node_id"]
    assert s.page.node(clone.metadata["promotion_label_node_id"]) is not None


@pytest.mark.skipif(not qt_renderer_available(), reason="Qt renderer not installed")
def test_reference_slots_render_png_offscreen(tmp_path: Path):
    s = session()
    create_item_slot(s, "individual-beta44", x=100, y=120)
    create_multi_item_strip(s, count=5, x=50, y=650)
    out = tmp_path / "beta45-ppt-reference.png"
    report = render_png(s.document, out, dpi=96)
    assert report.ok and out.stat().st_size > 1000
