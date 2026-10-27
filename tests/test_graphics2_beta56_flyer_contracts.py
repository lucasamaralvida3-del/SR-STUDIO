"""Beta56 full-flyer contracts: do not regress canonical editable slots."""
from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.campaign_tools import (
    DATE_PLACEMENTS, THEMES, update_campaign_date,
)
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.promotion_composition import apply_slot_composition
from srstudio.graphics2.promotion_layouts import plan_promotion


def router():
    return GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))


def test_transparent_campaign_background_preserves_original_individual_name_panel():
    r = router()
    a = r.dispatch({"name": "add_item_slot", "preset_id": "individual-beta44"})
    assert a.ok, a.message
    page = r.session.page
    slot = page.slots[a.payload["slot_id"]]
    for node_id in page.descendants(slot.metadata["root_node_id"]):
        node = page.node(node_id)
        if node.metadata.get("item_slot_background"):
            assert node.visible is False
        if node.metadata.get("item_slot_name_backdrop"):
            assert node.visible and node.style["fill"] == "#FFFFFF"
    m = r.dispatch({"name": "add_multi_item_slot", "count": 5})
    assert m.ok, m.message
    members = page.descendants(m.payload["root_node_id"])
    assert not any(page.node(nid).visible and page.node(nid).name == "Fundo branco da faixa"
                   for nid in members)
    assert any(page.node(nid).visible and page.node(nid).name == "Faixa azul contínua"
               for nid in members)


def test_unico_uses_exact_blue_reference_and_recolors_entire_card():
    r = router()
    added = r.dispatch({"name": "add_item_slot", "preset_id": "limpeza-blue-v1"})
    assert added.ok, added.message
    page = r.session.page
    slot = page.slots[added.payload["slot_id"]]
    assert slot.metadata["limpeza_blue_profile"] == "limpeza-blue-v1"
    changed = r.dispatch({"name": "set_slot_theme", "slot_id": slot.id, "theme": "churrasco"})
    assert changed.ok, changed.message
    assert slot.metadata["color_hex"] == THEMES["churrasco"]
    layers = [page.node(n) for n in page.descendants(slot.metadata["root_node_id"])]
    assert any(n.metadata.get("limpeza_blue_role") == "outer_frame"
               and n.style.get("fill") == THEMES["churrasco"] for n in layers)
    assert all(n.visible and n.style.get("fill") == "#FFFFFF" for n in layers
               if n.metadata.get("limpeza_blue_role") == "white_panel")


def test_nine_predefined_uses_real_multi5_instead_of_fake_four_individuals():
    r = router()
    plan = plan_promotion("nine")
    assert len(plan.placements) == 9
    assert [p.index for p in plan.placements] == list(range(9))
    result = apply_slot_composition(r.session, plan, reuse_existing=False)
    assert len(result.slot_ids) == 9
    roots = [n for n in r.session.page.nodes.values() if n.metadata.get("multi_slot_beta44")]
    assert len(roots) == 1
    assert roots[0].metadata["multi_count"] == 5
    assert len(roots[0].metadata["child_slot_ids"]) == 5


@pytest.mark.parametrize("campaign_id", list(DATE_PLACEMENTS))
def test_date_is_anchored_to_selected_campaign_and_uses_reference_font(campaign_id):
    session = GraphicsSession(GraphicsDocument())
    session.page.metadata["campaign_id"] = campaign_id
    session.document.metadata["data_promocao"] = "27/10/2026"
    date = update_campaign_date(session.document, session.page)
    assert date == "27/10/2026"
    node = session.page.node(session.page.metadata["campaign_date_node"])
    assert node.style["font_family"] == "Impact"
    assert node.style["align"] == "center"
    x, y, w, h = DATE_PLACEMENTS[campaign_id]
    assert node.transform.x == pytest.approx(session.page.width * x)
    assert node.transform.y == pytest.approx(session.page.height * y)
    assert node.transform.width == pytest.approx(session.page.width * w)
    assert node.transform.height == pytest.approx(session.page.height * h)


def test_multi_duplicate_and_whole_strip_resize():
    r = router()
    m = r.dispatch({"name": "add_multi_item_slot", "count": 5})
    assert m.ok
    src = m.payload["slot_ids"][0]
    result = r.dispatch({"name": "duplicate_slot", "slot_id": src})
    assert result.ok, result.message
    assert len(result.payload["slot_ids"]) == 5
    assert len(r.session.page.slots) == 10
    new_slot = r.session.page.slots[result.payload["slot_ids"][0]]
    root_id = new_slot.metadata["multi_parent_id"]
    root = r.session.page.node(root_id)
    rect = root.rect.normalized()
    changed = r.dispatch({"name": "adjust_smart_slot", "slot_id": new_slot.id,
                          "x": rect.x, "y": rect.y, "width": rect.width * .8,
                          "height": rect.height * .8, "snap": False})
    assert changed.ok, changed.message
    assert root.transform.width == pytest.approx(rect.width * .8)


def test_product_list_is_unbounded_and_image_bank_navigation_is_hidden():
    qml = (Path(__file__).resolve().parents[1] /
           "src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text("utf-8")
    assert "Ver mais produtos" not in qml
    assert ".slice(0, visibleProductLimit)" not in qml
    assert "wrapMode: Text.WordWrap" in qml
    assert "title:\"Imagens\"" not in qml
    assert '"name":"duplicate_slot"' in qml
    assert "placeSlotAt" in qml
    assert "inspectorAppPrice" in qml
