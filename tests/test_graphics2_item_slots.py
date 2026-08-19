from __future__ import annotations

from srstudio.graphics2.item_slots import (
    bind_product_to_item_slot,
    create_item_slot,
    duplicate_item_slot,
    item_slot_snapshot,
    list_item_slot_presets,
    refresh_item_slot_metadata,
    save_item_slot_as_preset,
    set_item_slot_role_bounds,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package


def _session() -> GraphicsSession:
    document = GraphicsDocument(name="ItemSlot test")
    document.add_page(GraphicsPage(name="Página 1", width=1080, height=1350))
    return GraphicsSession(document)


def test_builtin_presets_create_empty_multinode_item_slots() -> None:
    session = _session()
    assert {item["id"] for item in list_item_slot_presets(session.document)} >= {"destaque", "simples", "card"}

    for preset in ("destaque", "simples", "card"):
        slot = create_item_slot(session, preset, x=50, y=70)
        assert slot.metadata["manual_item_slot"] is True
        assert slot.metadata["preset_id"] == preset
        assert slot.product_id == ""
        assert slot.metadata["state"] == "empty"
        assert session.page.node(slot.metadata["root_node_id"]) is not None
        assert set(slot.node_by_role) >= {
            BindingRole.IMAGE.value,
            BindingRole.NAME.value,
            BindingRole.CURRENCY.value,
            BindingRole.PRICE_REAIS.value,
            BindingRole.PRICE_CENTS.value,
            BindingRole.UNIT.value,
        }
        price = slot.metadata["price_block"]
        assert price["currency_node"] == slot.node_by_role[BindingRole.CURRENCY.value]
        assert price["integer_node"] == slot.node_by_role[BindingRole.PRICE_REAIS.value]
        assert price["decimal_node"] == slot.node_by_role[BindingRole.PRICE_CENTS.value]
        assert price["unit_node"] == slot.node_by_role[BindingRole.UNIT.value]
        assert price["combined_value"] == ""


def test_move_and_resize_root_use_existing_group_geometry_and_persist() -> None:
    session = _session()
    slot = create_item_slot(session, "simples", x=100, y=150)
    root_id = slot.metadata["root_node_id"]
    before = item_slot_snapshot(session.page, slot)

    session.selection = {root_id}
    session.anchor_id = root_id
    session.move_selected(35, 45)
    moved = item_slot_snapshot(session.page, slot)
    assert moved["bounds"]["x"] == before["bounds"]["x"] + 35
    assert moved["bounds"]["y"] == before["bounds"]["y"] + 45

    root = session.page.node(root_id)
    assert root is not None
    session.resize_node(root_id, x=root.transform.x, y=root.transform.y, width=root.transform.width * 1.25, height=root.transform.height * 1.1)
    resized = item_slot_snapshot(session.page, slot)
    assert resized["bounds"]["width"] > moved["bounds"]["width"]
    assert resized["bounds"]["height"] > moved["bounds"]["height"]

    restored = GraphicsDocument.from_dict(session.document.to_dict())
    restored_slot = restored.active_page.slots[slot.id]
    assert item_slot_snapshot(restored.active_page, restored_slot)["bounds"] == resized["bounds"]


def test_internal_role_bounds_are_independent() -> None:
    session = _session()
    slot = create_item_slot(session, "destaque", x=40, y=50)
    before = item_slot_snapshot(session.page, slot)

    image = before["internal_roles"]["image"]
    assert set_item_slot_role_bounds(
        session,
        slot.id,
        "image",
        x=image["x"] + 10,
        y=image["y"] + 5,
        width=image["width"] - 20,
        height=image["height"] - 10,
    )
    after_image = item_slot_snapshot(session.page, slot)
    assert after_image["internal_roles"]["image"] != before["internal_roles"]["image"]
    for sibling in ("name", "price", "unit"):
        assert after_image["internal_roles"][sibling] == before["internal_roles"][sibling]

    for role in ("name", "price", "unit"):
        snap = item_slot_snapshot(session.page, slot)
        target = snap["internal_roles"][role]
        sibling_before = {
            key: value.copy()
            for key, value in snap["internal_roles"].items()
            if key != role
        }
        assert set_item_slot_role_bounds(
            session,
            slot.id,
            role,
            x=target["x"] + 3,
            y=target["y"] + 4,
            width=max(10, target["width"] - 6),
            height=max(10, target["height"] - 8),
        )
        updated = item_slot_snapshot(session.page, slot)
        for key, value in sibling_before.items():
            assert updated["internal_roles"][key] == value


def test_binding_changes_only_target_and_updates_price_block() -> None:
    session = _session()
    first = create_item_slot(session, "simples", x=40, y=50)
    second = create_item_slot(session, "simples", x=420, y=50)
    product = {"id": "p-1", "name": "Produto Teste", "price": "24.79", "unit": "KG", "image": "C:/images/product.png"}

    assert bind_product_to_item_slot(session, first.id, product)
    refresh_item_slot_metadata(session.page, first)
    assert first.product_id == "p-1"
    assert first.metadata["state"] == "filled"
    assert first.metadata["price_block"]["combined_value"] == "24.79"
    assert session.page.node(first.node_by_role[BindingRole.NAME.value]).text == "Produto Teste"
    assert session.page.node(first.node_by_role[BindingRole.PRICE_REAIS.value]).text == "24"
    assert session.page.node(first.node_by_role[BindingRole.PRICE_CENTS.value]).text == ",79"
    assert second.product_id == ""
    assert session.page.node(second.node_by_role[BindingRole.NAME.value]).text == "NOME DO PRODUTO"


def test_duplicate_filled_item_slot_defaults_to_structure_only_with_fresh_id() -> None:
    session = _session()
    source = create_item_slot(session, "card", x=70, y=80)
    bind_product_to_item_slot(session, source.id, {"id": "p-2", "name": "Carne", "price": "31.66", "unit": "KG", "image": "image.png"})

    clone = duplicate_item_slot(session, source.id)
    assert clone.id != source.id
    assert clone.metadata["root_node_id"] != source.metadata["root_node_id"]
    assert clone.metadata["preset_id"] == source.metadata["preset_id"]
    assert clone.product_id == ""
    assert clone.metadata["product_snapshot"] == {}
    assert clone.metadata["state"] == "empty"
    assert session.page.node(clone.node_by_role[BindingRole.NAME.value]).text == "NOME DO PRODUTO"
    assert session.page.node(clone.node_by_role[BindingRole.PRICE_REAIS.value]).text == "00"
    assert session.page.node(clone.node_by_role[BindingRole.PRICE_CENTS.value]).text == ",00"
    assert "bound_image_source" not in session.page.node(clone.node_by_role[BindingRole.IMAGE.value]).metadata
    assert source.product_id == "p-2"


def test_delete_removes_only_target_slot() -> None:
    session = _session()
    first = create_item_slot(session, "simples", x=40, y=50)
    second = create_item_slot(session, "simples", x=420, y=50)
    session.selection = {first.metadata["root_node_id"]}
    session.anchor_id = first.metadata["root_node_id"]
    assert session.delete_selected() > 0
    assert first.id not in session.page.slots
    assert second.id in session.page.slots


def test_save_slot_as_model_strips_product_and_preserves_structure() -> None:
    session = _session()
    slot = create_item_slot(session, "card", x=80, y=90)
    bind_product_to_item_slot(session, slot.id, {"id": "p-3", "name": "Bacon", "price": "18.76", "unit": "KG", "image": "bacon.png"})
    price = item_slot_snapshot(session.page, slot)["internal_roles"]["price"]
    set_item_slot_role_bounds(
        session,
        slot.id,
        "price",
        x=price["x"] - 7,
        y=price["y"] + 4,
        width=price["width"] + 14,
        height=price["height"],
    )

    preset = save_item_slot_as_preset(session, slot.id, "Meu Card")
    assert preset["name"] == "Meu Card"
    assert "product_id" not in preset
    assert "product_snapshot" not in preset
    clone = create_item_slot(session, preset["id"], x=500, y=90)
    assert clone.product_id == ""
    assert clone.metadata["state"] == "empty"


def test_save_close_reopen_package_preserves_manual_item_slot(tmp_path) -> None:
    session = _session()
    slot = create_item_slot(session, "destaque", x=100, y=120)
    bind_product_to_item_slot(session, slot.id, {"id": "p-4", "name": "Lombo", "price": "33.63", "unit": "KG"})
    name_area = item_slot_snapshot(session.page, slot)["internal_roles"]["name"]
    set_item_slot_role_bounds(
        session,
        slot.id,
        "name",
        x=name_area["x"] + 2,
        y=name_area["y"] + 3,
        width=name_area["width"] - 4,
        height=name_area["height"],
    )
    before = item_slot_snapshot(session.page, slot)

    output = tmp_path / "manual-item-slot.srscene"
    save_package(session.document, output, embed_local_assets=True)
    reopened = load_package(output, extract_assets_to=tmp_path / "assets")
    restored = reopened.active_page.slots[slot.id]
    refresh_item_slot_metadata(reopened.active_page, restored)
    after = item_slot_snapshot(reopened.active_page, restored)

    assert after["slot_id"] == before["slot_id"]
    assert after["preset_id"] == before["preset_id"]
    assert after["bounds"] == before["bounds"]
    assert after["internal_roles"] == before["internal_roles"]
    assert after["state"] == "filled"
    assert after["product_id"] == "p-4"
    assert after["price_block"]["combined_value"] == "33.63"
