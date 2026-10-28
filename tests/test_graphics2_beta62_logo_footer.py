"""G2 Beta62: real city-footer palette and non-overlapping campaign seals."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from srstudio.graphics2.builtin_campaign_catalog import builtin_campaign_assets
from srstudio.graphics2.campaign_tools import (
    _footer_color_from_image, apply_campaign_art, apply_campaign_preset,
    apply_slot_theme, logo_safe_reserve,
)
from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.slot_limpeza_blue import create_limpeza_blue_slot


# Swatches independently measured from the BAR at the bottom of the
# ORIGINAL poster artwork, never from the colored city text.
POSTER_FOOTER_COLORS = {
    "terca-verde": "#0A6005",
    "quarta-cafe": "#704A33",
    "quinta-file": "#460000",
    "churrasco": "#460000",
}


def _router_with_poster(campaign: str):
    router = ItemSlotCommandRouter(GraphicsSession(GraphicsDocument()))
    backdrop = next(
        a for a in builtin_campaign_assets()
        if a["kind"] == "background" and a["campaign_id"] == campaign)
    result = router.dispatch({
        "name": "apply_campaign_preset", "background_id": backdrop["id"]
    })
    assert result.ok, result.message
    return router, result.payload


@pytest.mark.parametrize("campaign,expected", POSTER_FOOTER_COLORS.items())
def test_original_poster_city_footer_swatch_is_real_image_color(campaign, expected):
    artwork = next(
        a for a in builtin_campaign_assets()
        if a["kind"] == "background" and a["campaign_id"] == campaign)
    extracted = _footer_color_from_image(artwork["path"])
    assert extracted is not None
    # The built-in WebP is encoded from the measured reference JPEG.
    assert max(abs(int(extracted[i:i + 2], 16) - int(expected[i:i + 2], 16))
               for i in (1, 3, 5)) <= 3


@pytest.mark.parametrize("campaign,expected", POSTER_FOOTER_COLORS.items())
@pytest.mark.parametrize("layout_mode,capacity", [("seven", 7), ("eleven", 11)])
def test_layout_avoids_actual_logo_and_colors_every_slot_like_its_footer(
        campaign, expected, layout_mode, capacity):
    router, applied = _router_with_poster(campaign)
    page = router.session.page
    original_logo = page.node(applied["seal_node_id"])
    original_bounds = original_logo.rect.normalized()
    image_id = original_logo.asset_id
    before_art = {
        "name": original_logo.name,
        "id": original_logo.id,
        "asset": image_id,
        "bounds": original_bounds,
    }
    out = router.dispatch({"name": "apply_promotion_layout",
                           "mode": layout_mode, "logo_reserved": .24})
    assert out.ok, out.message
    assert len(out.payload["slot_ids"]) == capacity
    assert page.metadata["slot_theme_color"] == expected
    assert all(page.slots[sid].metadata["color_hex"] == expected
               for sid in out.payload["slot_ids"])
    actual_logo = page.node(before_art["id"])
    assert actual_logo.rect.normalized() == before_art["bounds"]
    assert actual_logo.asset_id == before_art["asset"]
    assert actual_logo.name == before_art["name"]
    safe_bottom = original_bounds.bottom + page.height * .028
    for root_id in out.payload["root_node_ids"]:
        actual = page.node(root_id).rect.normalized()
        assert actual.y >= safe_bottom - .001
        assert actual.bottom <= page.height * .93 + .001
    for group in (n for n in page.nodes.values() if n.metadata.get("multi_slot_beta44")):
        ribbons = [page.node(n) for n in page.descendants(group.id)
                   if page.node(n).name == "Faixa azul contínua"]
        assert len(ribbons) == 1
        assert ribbons[0].style["fill"] == expected


def test_manually_enlarged_quinta_file_logo_keeps_position_and_is_protected():
    router, result = _router_with_poster("quinta-file")
    page = router.session.page
    seal = page.node(result["seal_node_id"])
    seal.transform.x = page.width * .40
    seal.transform.y = page.height * .06
    seal.transform.width = page.width * .57
    seal.transform.height = page.height * .33
    expected = seal.rect.normalized()
    assert logo_safe_reserve(page, .24) >= .418 - 1e-6
    applied = router.dispatch({
        "name": "apply_promotion_layout", "mode": "eleven", "logo_reserved": .24})
    assert applied.ok, applied.message
    assert seal.rect.normalized() == expected
    assert all(page.node(r).rect.y >= expected.bottom + page.height * .028 - .001
               for r in applied.payload["root_node_ids"])
    # Reapplying the SAME artwork must not revert the manual reference logo.
    preset = apply_campaign_preset(router.session, result["background_id"])
    assert preset["seal_node_id"] == seal.id
    assert seal.rect.normalized() == expected


def test_custom_campaign_footer_color_is_sampled_and_old_slot_redrawn(tmp_path):
    # Fully artificial background demonstrates that there is no hard-coded
    # Quinta-Filé shade when a different poster has its own city footer.
    backdrop = tmp_path / "custom-poster.png"
    im = Image.new("RGB", (1080, 1350), "#111111")
    from PIL import ImageDraw
    ImageDraw.Draw(im).rectangle((0, 1318, 1080, 1349), fill="#4F1739")
    im.save(backdrop)
    s = GraphicsSession(GraphicsDocument())
    apply_campaign_art(s, "background", str(backdrop), campaign_id="quinta-file")
    slot = create_limpeza_blue_slot(s)
    changed = apply_slot_theme(s, "quinta-file", entire_page=True)
    assert changed >= 1
    assert s.page.metadata["slot_theme_color"] == "#4F1739"
    assert slot.metadata["color_hex"] == "#4F1739"
    panels = [s.page.node(nid) for nid in
              s.page.descendants(slot.metadata["root_node_id"])
              if s.page.node(nid).metadata.get("limpeza_blue_role") == "white_panel"]
    assert panels and all(n.style["fill"] == "#FFFFFF" and n.visible for n in panels)
    assert _footer_color_from_image(str(backdrop)) == "#4F1739"


def test_oversized_logo_refuses_layout_without_changing_scene():
    router, result = _router_with_poster("quinta-file")
    page = router.session.page
    seal = page.node(result["seal_node_id"])
    seal.transform.y = page.height * .30
    seal.transform.height = page.height * .29
    before = router.session.document.to_dict()
    failed = router.dispatch({
        "name": "apply_promotion_layout", "mode": "seven", "logo_reserved": .15
    })
    assert not failed.ok
    assert "logo" in failed.message.lower()
    assert router.session.document.to_dict() == before
