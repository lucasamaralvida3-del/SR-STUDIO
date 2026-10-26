"""Executable UI-command contract for the campaign collections in Beta54."""
from pathlib import Path

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.campaign_tools import CAMPAIGNS, THEMES
import srstudio.graphics2.qt_host as qt_host


def test_accepted_campaigns_and_palettes_are_existing_slot_variants():
    assert set(CAMPAIGNS) == {"terca-verde", "quarta-cafe", "quinta-file", "churrasco"}
    assert all(name in THEMES for name in CAMPAIGNS)
    assert len({THEMES[name] for name in CAMPAIGNS}) == 4


def test_campaign_art_dispatch_accepts_qt_file_url_and_reuses_nodes(tmp_path: Path):
    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    background = tmp_path / "fundo sem data.jpg"
    seal = tmp_path / "selo cafe.png"
    background.write_bytes(b"test background")
    seal.write_bytes(b"test seal")
    first = router.dispatch({
        "name": "set_campaign_art", "kind": "background",
        "campaign_id": "quarta-cafe", "path": background.as_uri()})
    assert first.ok, first.message
    assert router.session.page.metadata["campaign_id"] == "quarta-cafe"
    assert "Quarta" in router.session.page.node(first.payload["node_id"]).name
    swapped = router.dispatch({
        "name": "set_campaign_art", "kind": "background",
        "campaign_id": "quinta-file", "path": background.as_uri()})
    assert swapped.ok, swapped.message
    assert swapped.payload["node_id"] == first.payload["node_id"]
    assert router.session.page.metadata["campaign_id"] == "quinta-file"
    other = router.dispatch({
        "name": "set_campaign_art", "kind": "seal",
        "campaign_id": "quinta-file", "path": seal.as_uri()})
    assert other.ok, other.message
    assert other.payload["node_id"] != swapped.payload["node_id"]
    assert len(router.session.document.assets) == 2
    rejected = router.dispatch({
        "name": "set_campaign_art", "kind": "seal",
        "campaign_id": "unrecognized", "path": seal.as_uri()})
    assert not rejected.ok
    assert router.session.page.metadata["campaign_id"] == "quinta-file"


def test_real_slot_and_layout_commands_are_not_unknown_commands():
    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    layout = router.dispatch({"name": "apply_promotion_layout", "mode": "individual", "reuse_existing": True})
    assert layout.ok, layout.message
    assert len(layout.payload["slot_ids"]) == 1
    sid = layout.payload["slot_ids"][0]
    assert sid in router.session.page.slots
    chosen = router.dispatch({"name": "set_slot_theme", "theme": "quarta-cafe", "entire_page": True})
    assert chosen.ok, chosen.message
    assert router.session.page.slots[sid].metadata["color_hex"] == THEMES["quarta-cafe"]
    price = router.dispatch({"name": "set_item_price_mode", "slot_id": sid, "mode": "two"})
    assert price.ok, price.message
    assert router.session.page.slots[sid].metadata["price_mode"] == "two"
    layout_again = router.dispatch({"name": "apply_promotion_layout", "mode": "individual", "reuse_existing": True})
    assert layout_again.ok, layout_again.message
    assert layout_again.payload["slot_ids"] == [sid]
    assert layout_again.payload["created_slot_ids"] == []


def test_multi_slot_and_date_commands_via_same_bridge():
    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    strip = router.dispatch({"name": "add_multi_item_slot", "count": 5, "price_mode": "two"})
    assert strip.ok, strip.message
    assert len(strip.payload["slot_ids"]) == 5
    date = router.dispatch({"name": "set_campaign_date", "mode": "manual", "value": "28/10/2026"})
    assert date.ok, date.message
    assert date.payload["date"] == "28/10/2026"
    assert router.session.page.metadata["campaign_date_display"] == "28/10/2026"


def test_qml_exposes_campaign_choice_and_warning_for_flattened_examples():
    source = (Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml").read_text("utf-8")
    for expected in ("campaignCampaignChoice", "Quarta Café com Pão",
                     "Quinta Filé", "Churrasco / Açougue", "preços ou datas gravados"):
        assert expected in source
