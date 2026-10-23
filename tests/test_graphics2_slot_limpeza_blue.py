from __future__ import annotations

import json

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import (
    create_item_slot, duplicate_item_slot, list_item_slot_presets,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.slot_limpeza_blue import (
    PRESET_ID, bind_product_to_limpeza_blue_slot, create_limpeza_blue_slot,
    inspect_limpeza_blue_slot,
)


def _session():
    doc = GraphicsDocument(name="Campanha Limpeza")
    doc.add_page(GraphicsPage(name="Ofertas", width=1080, height=1350))
    return GraphicsSession(doc)


def _text(page, node_id):
    node = page.node(str(node_id))
    assert node is not None
    return node.text


def _extra_text(page, slot, role):
    ids = slot.metadata["extra_bindings"][role]
    assert len(ids) == 1
    return _text(page, ids[0])


def test_single_slot_visible_in_editor_menu_and_recognizes_contract():
    session = _session()
    assert PRESET_ID in {p["id"] for p in list_item_slot_presets(session.document)}
    router = ItemSlotCommandRouter(session)
    result = json.loads(router.dispatch_json(
        json.dumps({"name": "add_item_slot", "preset_id": PRESET_ID, "x": 70, "y": 100}),
        include_scene_payload=False,
    ))
    assert result["ok"] is True
    slot = session.page.slots[result["payload"]["slot_id"]]
    assert len(session.page.slots) == 1  # overlays are not independent SmartSlots
    assert slot.metadata["single_slot_contract"]["area_count"] == 1
    assert set(slot.node_by_role) >= {
        BindingRole.IMAGE.value, BindingRole.NAME.value,
        BindingRole.PRICE_REAIS.value, BindingRole.PRICE_CENTS.value,
    }

    scan = inspect_limpeza_blue_slot(session.page, slot)
    assert scan["recognized"] is True
    assert scan["missing_roles"] == []
    probe = json.loads(router.dispatch_json(
        json.dumps({"name": "inspect_limpeza_blue_slot", "slot_id": slot.id}),
        include_scene_payload=False,
    ))
    assert probe["ok"] is True
    assert probe["payload"]["recognized"] is True

    # Relacoes espaciais independentes sao preservadas no card.
    bounds = {
        role: session.page.node(ids[0]).rect.normalized()
        for role, ids in slot.metadata["extra_bindings"].items()
    }
    assert bounds["promotion_label"].center_y < bounds["club_label"].center_y
    assert bounds["promotion_integer"].center_y < session.page.node(
        slot.node_by_role[BindingRole.PRICE_REAIS.value]
    ).rect.center_y


def test_bind_club_and_promotion_prices_independently():
    session = _session()
    slot = create_limpeza_blue_slot(session, x=15, y=25)
    assert bind_product_to_limpeza_blue_slot(session, slot.id, {
        "id": "sku-100", "name": "Lava roupas concentrado 5 L",
        "price": "129,99", "club_price": "119,99",
        "unit": "UN", "promotion_unit": "CADA",
    })
    page = session.page
    assert slot.product_id == "sku-100"
    assert _text(page, slot.node_by_role[BindingRole.NAME.value]) == "Lava roupas concentrado 5 L"
    assert _text(page, slot.node_by_role[BindingRole.PRICE_REAIS.value]) == "119"
    assert _text(page, slot.node_by_role[BindingRole.PRICE_CENTS.value]) == ",99"
    assert _extra_text(page, slot, "promotion_integer") == "129"
    assert _extra_text(page, slot, "promotion_cents") == ",99"
    assert _extra_text(page, slot, "promotion_unit") == "CADA"
    assert _extra_text(page, slot, "promotion_label") == "NA PROMOÇÃO"
    assert _extra_text(page, slot, "club_label") == "NO CLUBE"
    assert slot.metadata["price_block"]["combined_value"] == "119.99"


def test_deleting_required_role_invalidates_probe_without_mutation():
    session = _session()
    slot = create_limpeza_blue_slot(session)
    extra_id = slot.metadata["extra_bindings"]["promotion_cents"][0]
    session.page.remove_node(extra_id)
    count = len(session.page.nodes)
    report = inspect_limpeza_blue_slot(session.page, slot)
    assert report["recognized"] is False
    assert report["missing_roles"] == ["promotion_cents"]
    assert len(session.page.nodes) == count


def test_no_false_positive_for_generic_manual_item_slot():
    session = _session()
    slot = create_item_slot(session, "card")
    assert not inspect_limpeza_blue_slot(session.page, slot)["recognized"]


def test_duplicate_without_product_has_new_ids_and_empty_secondary_price():
    session = _session()
    original = create_limpeza_blue_slot(session)
    bind_product_to_limpeza_blue_slot(session, original.id, {
        "id": "sku-12", "name": "Produto 5 L", "price": "129,99",
        "club_price": "99,90", "unit": "UN",
    })
    clone = duplicate_item_slot(session, original.id, dx=20, dy=30)
    assert clone.id != original.id
    assert clone.product_id == ""
    assert clone.metadata["limpeza_blue_profile"] == PRESET_ID
    assert _extra_text(session.page, original, "promotion_integer") == "129"
    assert _extra_text(session.page, clone, "promotion_integer") == "00"
    assert _extra_text(session.page, clone, "promotion_cents") == ",00"
    assert set(original.metadata["extra_bindings"]["promotion_integer"]).isdisjoint(
        clone.metadata["extra_bindings"]["promotion_integer"]
    )
    assert inspect_limpeza_blue_slot(session.page, clone)["recognized"]


def test_roundtrip_keeps_one_slot_and_two_independent_price_fields(tmp_path):
    session = _session()
    slot = create_limpeza_blue_slot(session)
    bind_product_to_limpeza_blue_slot(session, slot.id, {
        "id": "p", "name": "Sabao Liquido", "price": "129,99",
        "club_price": "119,99", "unit": "UN",
    })
    target = tmp_path / "limpeza-blue.srscene"
    save_package(session.document, target, embed_local_assets=True)
    loaded = load_package(target, extract_assets_to=tmp_path / "assets")
    assert len(loaded.active_page.slots) == 1
    restored = loaded.active_page.slots[slot.id]
    assert inspect_limpeza_blue_slot(loaded.active_page, restored)["recognized"]
    assert _extra_text(loaded.active_page, restored, "promotion_integer") == "129"
    assert _text(loaded.active_page, restored.node_by_role[BindingRole.PRICE_REAIS.value]) == "119"
