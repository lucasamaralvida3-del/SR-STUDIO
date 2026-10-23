from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.item_slots import refresh_all_item_slots
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.slot_limpeza_blue import (
    LAYERS,
    PRESET_ID,
    bind_product_to_limpeza_blue_slot,
    create_limpeza_blue_slot,
    inspect_limpeza_blue_slot,
)


def _session():
    document = GraphicsDocument(name="Slot Limpeza V2")
    document.add_page(GraphicsPage(name="Teste", width=1080, height=1350))
    return GraphicsSession(document)


def _node(page, slot, role):
    if role in slot.metadata.get("extra_bindings", {}):
        return page.node(slot.metadata["extra_bindings"][role][0])
    if role in slot.node_by_role:
        return page.node(slot.node_by_role[role])
    for raw_id in slot.metadata.get("limpeza_blue_nodes", []):
        node = page.node(raw_id)
        if node is not None and node.metadata.get("limpeza_blue_role") == role:
            return node
    return None


def test_product_is_behind_both_price_backgrounds_and_all_prices_are_visible():
    session = _session()
    slot = create_limpeza_blue_slot(session)
    page = session.page
    image = _node(page, slot, BindingRole.IMAGE.value)
    main_bg = _node(page, slot, "club_background")
    secondary_bg = _node(page, slot, "promotion_background")
    main_integer = _node(page, slot, BindingRole.PRICE_REAIS.value)
    promo_integer = _node(page, slot, "promotion_integer")
    title = _node(page, slot, BindingRole.NAME.value)
    assert all(node is not None for node in (image, main_bg, secondary_bg, main_integer, promo_integer, title))
    assert image.z_index < main_bg.z_index < main_integer.z_index
    assert image.z_index < secondary_bg.z_index < promo_integer.z_index
    assert title.z_index > promo_integer.z_index
    assert main_bg.locked and secondary_bg.locked
    assert slot.metadata["limpeza_blue_version"] == 2
    assert inspect_limpeza_blue_slot(page, slot)["recognized"] is True


def test_slot_v2_matches_reference_geometry_and_condensed_font():
    session = _session()
    slot = create_limpeza_blue_slot(session, x=20, y=45)
    page = session.page
    root = page.node(slot.metadata["root_node_id"]).rect.normalized()
    outer = _node(page, slot, "outer_frame").rect.normalized()
    panel = _node(page, slot, "white_panel").rect.normalized()
    club = _node(page, slot, "club_background").rect.normalized()
    promo = _node(page, slot, "promotion_background").rect.normalized()
    assert abs(outer.width / root.width - 0.75) < 0.001
    assert panel.x > outer.x and panel.y > outer.y
    assert club.right > outer.right and club.bottom > panel.bottom
    assert promo.y < club.y
    for role in ("promotion_label", "promotion_integer", "promotion_cents", "club_label"):
        node = _node(page, slot, role)
        assert node.style["font_family"] == "Impact"
    assert _node(page, slot, BindingRole.NAME.value).style["font_family"] == "Impact"
    assert _node(page, slot, BindingRole.PRICE_REAIS.value).style["font_family"] == "Impact"


def test_existing_v1_slot_migrates_once_without_losing_product_or_saved_prices(tmp_path):
    session = _session()
    slot = create_limpeza_blue_slot(session)
    product = {
        "id": "papel-fofinho", "name": "PAPEL HIG FOFINHO NAT FD NEUTRO 12X1",
        "price": "18,43", "club_price": "17,92", "unit": "UN",
        "promotion_unit": "CADA",
    }
    assert bind_product_to_limpeza_blue_slot(session, slot.id, product)
    page = session.page
    image = _node(page, slot, BindingRole.IMAGE.value)
    bg = _node(page, slot, "club_background")
    image.z_index = 0
    bg.z_index = -40
    slot.metadata["limpeza_blue_version"] = 1

    refresh_all_item_slots(session.document)
    assert image.z_index == LAYERS["image"]
    assert bg.z_index == LAYERS["club_background"]
    assert slot.metadata["limpeza_blue_version"] == 2
    assert slot.product_id == "papel-fofinho"
    assert _node(page, slot, "promotion_integer").text == "18"
    assert _node(page, slot, BindingRole.PRICE_REAIS.value).text == "17"
    snapshot = session.document.to_dict()
    refresh_all_item_slots(session.document)
    assert snapshot == session.document.to_dict(), "Repeated payload refresh must not mutate layout"

    path = tmp_path / "limpeza-v2.srscene"
    save_package(session.document, path, embed_local_assets=True)
    restored = load_package(path, extract_assets_to=tmp_path / "assets")
    recovered_slot = restored.active_page.slots[slot.id]
    assert recovered_slot.metadata["limpeza_blue_version"] == 2
    assert inspect_limpeza_blue_slot(restored.active_page, recovered_slot)["recognized"]


def test_image_inspector_does_not_decode_full_scene_in_computed_visibility():
    root = Path(__file__).resolve().parents[1]
    qml = (root / "src/srstudio/graphics2/qml/ImageInspector.qml").read_text(encoding="utf-8")
    assert "readonly property bool bridgeHasImageSelection: hasImageSelection" in qml
    assert qml.count("JSON.parse(sceneBridge.sceneJson)") == 1
    assert "onPressedChanged: if (!pressed) applyFraming()" in qml
