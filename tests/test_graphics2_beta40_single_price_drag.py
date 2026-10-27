from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.item_slots import list_item_slot_presets
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.slot_limpeza_blue import create_limpeza_blue_slot, bind_product_to_limpeza_blue_slot
from srstudio.graphics2.smart_slot_manual import set_manual_slot_bounds


def _new():
    document = GraphicsDocument(name="Um ou dois preços")
    document.add_page(GraphicsPage(width=1080,height=1350,name="Encarte"))
    session = GraphicsSession(document)
    slot = create_limpeza_blue_slot(session, x=150, y=260)
    return session, slot


def _role(page, slot, name):
    for node_id in page.descendants(str(slot.metadata["root_node_id"])):
        node = page.node(node_id)
        if node and node.metadata.get("limpeza_blue_role") == name:
            return node
    raise AssertionError(name)


def test_one_price_hides_secondary_promotion_and_club_caption():
    session, slot = _new()
    assert bind_product_to_limpeza_blue_slot(session, slot.id, {
        "id":"farinha", "name":"FLOCÃO DE MILHO SINHÁ 400G",
        "price":"2,18", "unit":"UN",
    })
    p = session.page
    assert slot.metadata["limpeza_blue_price_mode"] == "one"
    assert slot.metadata["secondary_price_visible"] is False
    assert p.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).text == "2"
    for role in ("promotion_background", "promotion_label", "promotion_currency",
                 "promotion_integer", "promotion_cents", "promotion_unit", "club_label"):
        assert _role(p, slot, role).visible is False, role
    assert list_item_slot_presets(session.document)[0]["id"] == "limpeza-blue-v1"


def test_two_prices_restore_badge_and_club_with_same_slot_id_and_nodes():
    session, slot = _new()
    before = {role: list(ids) for role,ids in slot.metadata["extra_bindings"].items()}
    assert bind_product_to_limpeza_blue_slot(session, slot.id, {"id":"one","name":"ARROZ","price":"22,90"})
    assert bind_product_to_limpeza_blue_slot(session, slot.id, {
        "id":"two","name":"ARROZ","price":"22,90","club_price":"19,90"
    })
    assert slot.metadata["limpeza_blue_price_mode"] == "two"
    assert _role(session.page, slot, "promotion_background").visible
    assert _role(session.page, slot, "club_label").visible
    assert slot.metadata["extra_bindings"] == before
    assert len(session.page.slots) == 1
    assert session.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).text == "19"
    assert _role(session.page, slot, "promotion_integer").text == "22"


def test_equal_price_formats_do_not_create_a_fake_promotion():
    session, slot = _new()
    assert bind_product_to_limpeza_blue_slot(session, slot.id, {
        "id":"equal","name":"CAFÉ","price":"18,43","club_price":"18.43"
    })
    assert slot.metadata["limpeza_blue_price_mode"] == "one"


def test_real_root_and_all_artwork_translate_once_after_manual_resize():
    session, slot = _new()
    root = session.page.node(slot.metadata["root_node_id"])
    image = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    original = root.rect.normalized()
    ix, iy = image.transform.x,image.transform.y
    set_manual_slot_bounds(session, slot.id, x=original.x+125,y=original.y+90,
                           width=original.width*1.2,height=original.height*1.1)
    assert root.transform.x == original.x+125
    assert root.transform.y == original.y+90
    assert abs(image.transform.x-(original.x+125+(ix-original.x)*1.2))<0.01
    assert abs(image.transform.y-(original.y+90+(iy-original.y)*1.1))<0.01
    set_manual_slot_bounds(session,slot.id,x=original.x+135,y=original.y+100,
                           width=original.width*1.2,height=original.height*1.1)
    assert root.transform.x == original.x+135
    assert root.transform.y == original.y+100
    assert len(session.page.slots) == 1


def test_editor_does_not_steal_image_mouse_press_and_aligns_slot_outline():
    qml = (Path(__file__).resolve().parents[1]/
           "src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    assert "slot.metadata.multi_parent_id || slot.metadata.root_node_id" in qml
    assert "enabled: smartSlotEditMode || productDragActive" in qml
    assert "enabled: !smartSlotEditMode && !effectiveLocked(modelData)" in qml
    assert "Selecting on press emitted sceneChanged" in qml
    assert "Remover Fundo" in qml
    assert "Object.values(page.slots || {}).filter" in qml
