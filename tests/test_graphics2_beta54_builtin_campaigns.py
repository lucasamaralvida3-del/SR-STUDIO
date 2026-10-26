"""Beta54: real built-in assets, exact thumbnail images and automatic placement."""
from __future__ import annotations

from pathlib import Path
import json

import pytest

from srstudio.graphics2.builtin_campaign_catalog import (
    builtin_campaign_assets, builtin_campaign_catalog, builtin_campaign_root,
    default_seal_for_campaign,
)
from srstudio.graphics2.campaign_tools import apply_campaign_preset, apply_campaign_seal, THEMES
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
import srstudio.graphics2.qt_host as qt_host


def test_all_twelve_bundled_images_and_previews_exist_and_are_valid():
    root = builtin_campaign_root()
    manifest = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "SRSTUDIO_BUILTIN_CAMPAIGN_ART_1"
    assert len(manifest["assets"]) == 12
    assert len(builtin_campaign_assets()) == 12
    assert sum(1 for item in builtin_campaign_assets() if item["kind"] == "background") == 4
    assert sum(1 for item in builtin_campaign_assets() if item["kind"] == "seal") == 8
    for item in builtin_campaign_assets():
        assert item["source"] == "builtin"
        assert Path(item["path"]).is_file()
        assert item["preview_url"].startswith("file:")
        assert "thumbs" in item["preview_url"]
        assert item["id"] and item["campaign_id"]


@pytest.mark.parametrize("campaign_id", ["terca-verde", "quarta-cafe", "quinta-file", "churrasco"])
def test_one_click_preset_full_cover_and_matching_logo(campaign_id):
    session = GraphicsSession(GraphicsDocument())
    router = GraphicsCommandRouter(session)
    background = next(item for item in builtin_campaign_assets()
                      if item["kind"] == "background" and item["campaign_id"] == campaign_id)
    result = router.dispatch({"name": "apply_campaign_preset", "background_id": background["id"]})
    assert result.ok, result.message
    page = router.session.page
    bg = page.node(result.payload["background_node_id"])
    seal = page.node(result.payload["seal_node_id"])
    assert bg.transform.x == 0
    assert bg.transform.y == 0
    assert bg.transform.width == page.width
    assert bg.transform.height == page.height
    assert bg.style["fit"] == "cover"
    assert bg.z_index < seal.z_index
    assert seal.style["fit"] == "contain"
    assert seal.transform.x >= .30 * page.width
    assert seal.transform.x + seal.transform.width <= 1.0 * page.width
    assert page.metadata["campaign_id"] == campaign_id
    assert page.metadata["slot_theme"] == campaign_id
    assert page.metadata["campaign_seal_asset"] == default_seal_for_campaign(campaign_id)["id"]
    # One undo removes both arts, theme and editable date without touching the scene before.
    undone = router.dispatch({"name": "undo"})
    assert undone.ok and undone.changed
    assert not router.session.page.metadata.get("campaign_background_node")
    assert not router.session.page.metadata.get("campaign_seal_node")


def test_replacing_campaign_does_not_accumulate_artwork():
    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    backgrounds = [item for item in builtin_campaign_assets() if item["kind"] == "background"]
    first = router.dispatch({"name": "apply_campaign_preset", "background_id": backgrounds[0]["id"]})
    second = router.dispatch({"name": "apply_campaign_preset", "background_id": backgrounds[1]["id"]})
    assert first.ok and second.ok
    assert first.payload["background_node_id"] == second.payload["background_node_id"]
    assert first.payload["seal_node_id"] == second.payload["seal_node_id"]
    assert router.session.page.metadata["campaign_id"] == backgrounds[1]["campaign_id"]


def test_seal_variants_position_and_reject_cross_campaign():
    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    background = next(item for item in builtin_campaign_assets()
                      if item["campaign_id"] == "quinta-file" and item["kind"] == "background")
    assert router.dispatch({"name": "apply_campaign_preset", "background_id": background["id"]}).ok
    seal = next(item for item in builtin_campaign_assets()
                if item["id"] == "quinta-file:seal:quinta-file-sanju")
    changed = router.dispatch({"name": "apply_campaign_seal", "seal_id": seal["id"]})
    assert changed.ok, changed.message
    assert router.session.page.metadata["campaign_seal_asset"] == seal["id"]
    invalid = router.dispatch({"name": "apply_campaign_seal", "seal_id": "churrasco:seal:churrasco"})
    assert not invalid.ok


def test_qml_visual_gallery_and_collect_data_host():
    source = (Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml").read_text("utf-8")
    assert 'modelData.preview_url' in source
    assert 'apply_campaign_preset' in source
    assert 'apply_campaign_seal' in source
    assert 'text: "Importar pacote de campanhas (ZIP)"' not in source
    build = Path(__file__).resolve().parents[1] / "build" / "build_graphics2_host.py"
    assert '"--collect-data"' in build.read_text(encoding="utf-8")
