"""Regression against the Oct 27 screenshot and original PowerPoint models."""
import os
from copy import deepcopy
from dataclasses import asdict

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
import pytest
pytest.importorskip("PySide6")
from PySide6 import QtCore, QtGui
from srstudio.graphics2.model import GraphicsDocument, BindingRole
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.item_slots import create_item_slot, bind_product_to_item_slot, refresh_all_item_slots
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.campaign_tools import apply_slot_theme
from srstudio.graphics2.qt_renderer import _draw_text

@pytest.fixture(scope="module", autouse=True)
def app():
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    # Windows' offscreen plugin can expose no system fonts. Load the real
    # installed font so Alpha43's offscreen run cannot measure tofu boxes.
    if os.name == "nt" and "Impact" not in QtGui.QFontDatabase.families():
        assert QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/impact.ttf") >= 0
    font = QtGui.QFont("Impact" if os.name == "nt" else "DejaVu Sans")
    assert QtGui.QFontMetricsF(font).inFontUcs4(ord("3"))
    yield app

def product():
    return {"id": "OMO", "name": "SABÃO EM PÓ OMO 2,2KG", "price": "32,86", "club_price": "31,99", "unit": "UN"}

def test_original_white_panels_survive_campaign_and_saved_beta56_repair():
    r = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    for preset in ("limpeza-blue-v1", "individual-beta44"):
        added = r.dispatch({"name": "add_item_slot", "preset_id": preset})
        assert added.ok
        if preset == "individual-beta44":
            bind_product_to_item_slot(r.session, added.payload["slot_id"], product())
    apply_slot_theme(r.session, "quarta-cafe", entire_page=True)
    panels = [n for n in r.session.page.nodes.values() if n.metadata.get("limpeza_blue_role") == "white_panel" or n.metadata.get("item_slot_name_backdrop")]
    assert len(panels) == 2
    assert all(n.visible and n.style["fill"] == "#FFFFFF" for n in panels)
    for n in panels:
        n.visible = False
    for slot in r.session.page.slots.values():
        slot.metadata.pop("slot_art_revision", None)
        slot.metadata["two_price_reference_revision"] = 51
    saved = GraphicsDocument.from_dict(r.session.document.to_dict())
    ids = set(saved.active_page.nodes)
    refresh_all_item_slots(saved)
    assert all(saved.active_page.node(n.id).visible for n in panels)
    assert set(saved.active_page.nodes) == ids
    first = saved.to_dict()
    refresh_all_item_slots(saved)
    assert saved.to_dict() == first

def test_unico_created_after_campaign_has_colored_shapes_and_white_text():
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    r = ItemSlotCommandRouter(GraphicsSession(GraphicsDocument()))
    apply_slot_theme(r.session, "quarta-cafe", entire_page=True)
    added = r.dispatch({"name": "add_item_slot", "preset_id": "limpeza-blue-v1"})
    assert added.ok
    shapes = [n for n in r.session.page.nodes.values() if n.metadata.get("limpeza_blue_role") in ("outer_frame", "promotion_background", "club_background")]
    assert len(shapes) == 3
    assert all(n.style["fill"] == "#78441F" for n in shapes)

def ink_bounds(node):
    n = deepcopy(node)
    n.transform.x = n.transform.y = 5
    image = QtGui.QImage(1000, 400, QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    _draw_text(painter, n, QtCore, QtGui)
    painter.end()
    points = [(x,y) for y in range(400) for x in range(1000) if image.pixelColor(x,y).alpha() > 64]
    assert points
    return (min(x for x,y in points)-5+node.transform.x, max(x for x,y in points)-5+node.transform.x)

@pytest.mark.parametrize("count", [5,6])
@pytest.mark.parametrize("value", ["3,99", "31,99", "131,99"])
def test_multi_rendered_cents_are_adjacent_and_unit_is_under_cents(count, value):
    s = GraphicsSession(GraphicsDocument())
    strip = create_multi_item_strip(s, count=count)
    slot = s.page.slots[strip["slot_ids"][0]]
    p = product(); p["club_price"] = value
    bind_product_to_item_slot(s, slot.id, p)
    integer = s.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value])
    cents = s.page.node(slot.node_by_role[BindingRole.PRICE_CENTS.value])
    unit = s.page.node(slot.node_by_role[BindingRole.UNIT.value])
    club = s.page.node(slot.metadata["club_label_node_id"])
    root = s.page.node(slot.metadata["root_node_id"])
    gap = ink_bounds(cents)[0] - ink_bounds(integer)[1]
    assert 0 < gap < root.rect.width * .035, gap
    assert abs(unit.rect.center_x - cents.rect.center_x) < root.rect.width * .04
    assert unit.rect.y > cents.rect.bottom
    assert unit.rect.right < club.rect.x
    assert club.transform.rotation == 90 and club.text == "NO CLUBE SR"


@pytest.mark.parametrize("count", [5, 6])
def test_multi_move_resize_roundtrip_preserves_all_prices_and_relative_positions(tmp_path, count):
    from srstudio.graphics2.package import save_package, load_package
    s = GraphicsSession(GraphicsDocument())
    strip = create_multi_item_strip(s, count=count)
    for sid in strip["slot_ids"]:
        bind_product_to_item_slot(s, sid, product())
    root = s.page.node(strip["root_node_id"])
    original = {nid: asdict(s.page.node(nid)) for nid in s.page.descendants(root.id)}
    old = root.rect
    s.select(root.id)
    s.move_selected(21, -33)
    s.resize_node(root.id, width=old.width*.8, height=old.height*.8)
    for nid, before in original.items():
        node = s.page.node(nid)
        t = before["transform"]
        assert node.rect.x == pytest.approx(old.x+21+(t["x"]-old.x)*.8)
        assert node.rect.y == pytest.approx(old.y-33+(t["y"]-old.y)*.8)
        assert node.rect.width == pytest.approx(t["width"]*.8)
        assert node.rect.height == pytest.approx(t["height"]*.8)
        assert node.text == before["text"]
    moved = s.document.to_dict()
    assert s.undo() and s.redo()
    assert s.document.to_dict() == moved
    target = save_package(s.document, tmp_path / "multi.srscene")
    saved = load_package(target)
    refresh_all_item_slots(saved)
    assert set(saved.active_page.slots) == set(strip["slot_ids"])
    for sid in strip["slot_ids"]:
        slot = saved.active_page.slots[sid]
        assert slot.product_id == "OMO"
        assert slot.metadata["original_product_snapshot"] == product()
        assert saved.active_page.node(slot.node_by_role["price_reais"]).text == "31"
        assert saved.active_page.node(slot.node_by_role["price_cents"]).text == ",99"
        assert saved.active_page.node(slot.node_by_role["retail_price"]).text == "R$ 32,86"
    for nid in original:
        assert saved.active_page.node(nid).transform == s.page.node(nid).transform


def test_create_themed_unico_is_one_undo_action():
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    s = GraphicsSession(GraphicsDocument())
    apply_slot_theme(s, "quarta-cafe", entire_page=True)
    before = s.document.to_dict()
    r = ItemSlotCommandRouter(s)
    assert r.dispatch({"name": "add_item_slot", "preset_id": "limpeza-blue-v1"}).ok
    assert s.undo()
    assert s.document.to_dict() == before


@pytest.mark.parametrize("preset", ["limpeza-blue-v1", "individual-beta44", "multi-cell-beta44"])
def test_explicit_promotion_and_club_prices_are_not_replaced_by_retail(preset):
    from srstudio.graphics2.slot_limpeza_blue import create_limpeza_blue_slot, bind_product_to_limpeza_blue_slot
    s = GraphicsSession(GraphicsDocument())
    p = {**product(), "price": "35,90", "promotion_price": "32,86"}
    if preset == "limpeza-blue-v1":
        slot = create_limpeza_blue_slot(s)
        assert bind_product_to_limpeza_blue_slot(s, slot.id, p)
        promo = s.page.node(slot.metadata["extra_bindings"]["promotion_integer"][0]).text
        assert promo == "32"
    else:
        slot = create_item_slot(s, preset)
        assert bind_product_to_item_slot(s, slot.id, p)
        assert s.page.node(slot.node_by_role["retail_price"]).text == "R$ 32,86"
    assert s.page.node(slot.node_by_role["price_reais"]).text == "31"
    assert s.page.node(slot.node_by_role["price_cents"]).text == ",99"


def test_multi_one_price_digits_do_not_overlap_after_two_price_toggle():
    from srstudio.graphics2.item_slots import set_reference_price_mode
    s = GraphicsSession(GraphicsDocument())
    strip = create_multi_item_strip(s, count=6)
    sid = strip["slot_ids"][0]
    bind_product_to_item_slot(s, sid, {**product(), "price": "31,99", "club_price": ""})
    for mode in ("one", "two", "one"):
        set_reference_price_mode(s, [sid], mode)
        slot = s.page.slots[sid]
        integer = s.page.node(slot.node_by_role["price_reais"])
        cents = s.page.node(slot.node_by_role["price_cents"])
        assert ink_bounds(integer)[1] < ink_bounds(cents)[0]
