"""Beta53 campaign and Smart Slot regressions from Terça Verde references."""
from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.model import BindingRole, GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.item_slots import create_item_slot, set_reference_price_mode
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.campaign_tools import (
    BLUE, GREEN, apply_campaign_art, apply_slot_theme, detect_sheet_date,
    parse_promo_date, set_campaign_date,
)
from srstudio.graphics2.promotion_layouts import plan_promotion
import srstudio.graphics2.qt_host as qt_host


def test_pptx_nine_layout_preserves_hero_four_right_and_four_bottom():
    plan = plan_promotion("nine", logo_reserved=.24)
    assert len(plan.placements) == 9
    hero = plan.placements[0]
    assert hero.width > plan.placements[1].width
    assert [p.index for p in plan.placements] == list(range(9))
    assert len({p.y for p in plan.placements[5:]}) == 1


def test_vertical_clube_multi_and_horizontal_individual():
    doc = GraphicsDocument()
    session = GraphicsSession(doc)
    individual = create_item_slot(session, "individual-beta44")
    strip = create_multi_item_strip(session, count=5, price_mode="two")
    assert len(strip["slot_ids"]) == 5
    set_reference_price_mode(session, strip["slot_ids"], "two")
    set_reference_price_mode(session, [individual.id], "two")
    for sid, expected in [(individual.id, 0)] + [(s, 90) for s in strip["slot_ids"]]:
        slot = session.page.slots[sid]
        club = session.page.node(slot.metadata["club_label_node_id"])
        assert club is not None
        assert club.text == "NO CLUBE SR"
        assert club.visible
        assert club.style["single_line"] is True
        assert club.transform.rotation == expected


def test_theme_applies_to_existing_slot_and_multi_without_new_family():
    doc = GraphicsDocument()
    session = GraphicsSession(doc)
    solo = create_item_slot(session, "individual-beta44")
    multi = create_multi_item_strip(session, count=5)
    ids = [solo.id] + multi["slot_ids"]
    old_ids = set(session.page.slots)
    assert apply_slot_theme(session, "terca-verde", entire_page=True) == len(ids)
    assert set(session.page.slots) == old_ids
    assert all(session.page.slots[sid].metadata["color_hex"] == GREEN for sid in ids)
    root = session.page.node(multi["root_node_id"])
    footer = next(session.page.node(x) for x in session.page.descendants(root.id)
                  if session.page.node(x).name == "Faixa azul contínua")
    assert footer.style["fill"] == GREEN
    set_reference_price_mode(session, [solo.id], "two")
    plate = next(session.page.node(x) for x in session.page.descendants(
        session.page.slots[solo.id].metadata["root_node_id"])
        if session.page.node(x).metadata.get("item_slot_price_background"))
    assert plate.style["fill"] == GREEN
    assert apply_slot_theme(session, "azul", entire_page=True) == len(ids)
    assert footer.style["fill"] == BLUE


def test_custom_color_stays_editable_and_validated():
    session = GraphicsSession(GraphicsDocument())
    slot = create_item_slot(session, "individual-beta44")
    assert apply_slot_theme(session, "#ffcc00", [slot.id]) == 1
    assert slot.metadata["color_hex"] == "#FFCC00"
    with pytest.raises(ValueError):
        apply_slot_theme(session, "blue; DROP TABLE", [slot.id])


def test_campaign_date_manual_automatic_and_missing_are_not_guessed():
    doc = GraphicsDocument()
    session = GraphicsSession(doc)
    assert parse_promo_date("2026-10-13") == "13/10/2026"
    assert parse_promo_date("13/10/2026") == "13/10/2026"
    assert set_campaign_date(session, mode="auto") == ""
    doc.metadata["products"] = [{"id": "banana", "VALIDADE": "13/10/2026"}]
    assert detect_sheet_date(doc) == "13/10/2026"
    assert set_campaign_date(session, mode="auto") == "13/10/2026"
    assert set_campaign_date(session, mode="manual", value="28/10/2026") == "28/10/2026"
    with pytest.raises(ValueError):
        set_campaign_date(session, mode="manual", value="31/02/2026")
    assert set_campaign_date(session, mode="auto") == "13/10/2026"
    doc.metadata["products"].append({"VALIDADE": "14/10/2026"})
    assert set_campaign_date(session, mode="auto") == ""


def test_campaign_art_replacement_is_idempotent_and_uses_supplied_file(tmp_path: Path):
    doc = GraphicsDocument()
    session = GraphicsSession(doc)
    background = tmp_path / "fundo-sem-data.jpg"
    seal = tmp_path / "selo-terca.png"
    background.write_bytes(b"test-local-image-content")
    seal.write_bytes(b"test-local-seal-content")
    node_id = apply_campaign_art(session, "background", background)
    assert apply_campaign_art(session, "background", background) == node_id
    seal_id = apply_campaign_art(session, "seal", seal)
    assert node_id != seal_id
    assert session.page.node(node_id).z_index < 0
    assert session.page.node(seal_id).transform.x > doc.active_page.width * .30
    assert len(doc.assets) == 2
    assert session.page.node(node_id).asset_id in doc.assets
    assert session.page.node(seal_id).asset_id in doc.assets
    with pytest.raises(ValueError):
        apply_campaign_art(session, "seal", tmp_path / "missing.png")


def test_qml_has_campaign_editor_and_true_multi_previews():
    source = (Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml").read_text(encoding="utf-8")
    for term in ("Fundos Promocionais", "Selos Promocionais", "set_slot_theme",
                 "set_campaign_date", "set_campaign_art", "layout-nine"):
        # Layout is listed as a raw mode in the actual model, not this exact ID.
        assert (term in source if term != "layout-nine" else '"mode":"nine"' in source)
    assert "id: multiPreviewCard" not in source
