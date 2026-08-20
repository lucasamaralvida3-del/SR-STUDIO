from __future__ import annotations

from srstudio.graphics2 import BindingRole, GraphicsCommandRouter, GraphicsSession


def _slot_node(session: GraphicsSession, slot_id: str, role: str):
    slot = session.page.slots[slot_id]
    node_id = slot.node_by_role.get(role)
    if node_id:
        return session.page.node(node_id)
    extras = dict(slot.metadata.get("extra_bindings") or {})
    values = list(extras.get(role) or [])
    return session.page.node(values[0]) if values else None


def test_drop_product_reenters_wrapped_bind_command_and_preserves_payload():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch(
        {
            "name": "create_product_card",
            "x": 100,
            "y": 100,
            "width": 420,
            "height": 360,
            "include_app_price": True,
        }
    )
    slot_id = str(created.payload["slot_id"])

    result = router.dispatch(
        {
            "name": "drop_product",
            "x": 250,
            "y": 220,
            "product": {
                "id": "drop-1",
                "display_name": "ARROZ 5KG",
                "price": "24,90",
                "app_price": "23,49",
                "unit": "UN",
            },
        }
    )

    assert result.ok is True
    assert result.changed is True
    assert result.payload["slot_id"] == slot_id
    assert result.payload["product_id"] == "drop-1"
    assert result.payload["drop_target"]["slot_id"] == slot_id
    assert result.payload["drop_target"]["inside"] is True
    assert session.page.slots[slot_id].product_id == "drop-1"
    assert _slot_node(session, slot_id, "name").text == "ARROZ 5KG"
    assert _slot_node(session, slot_id, "price_complete").text == "24,90"
    assert _slot_node(session, slot_id, "app_price_complete").text == "23,49"


def test_explicit_rebind_reactivates_detached_visual_nodes():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch(
        {
            "name": "create_product_card",
            "include_image": False,
            "include_description": False,
            "include_quantity": False,
        }
    )
    old_slot_id = str(created.payload["slot_id"])
    old_slot = session.page.slots[old_slot_id]
    bindings = dict(old_slot.node_by_role)

    removed = router.dispatch(
        {"name": "remove_smart_slot", "slot_id": old_slot_id, "delete_nodes": False}
    )
    assert removed.ok and removed.changed
    assert all(session.page.node(node_id).metadata.get("smart_slot_detached") for node_id in bindings.values())

    replacement = session.create_slot(
        "Religado",
        {
            BindingRole.NAME: bindings["name"],
            BindingRole.CURRENCY: bindings["price_currency"],
            BindingRole.UNIT: bindings["unit"],
        },
    )
    result = router.dispatch(
        {
            "name": "rebind_slot",
            "slot_id": replacement.id,
            "bindings": bindings,
        }
    )

    assert result.ok is True
    assert result.changed is True
    for node_id in bindings.values():
        node = session.page.node(node_id)
        assert "smart_slot_detached" not in node.metadata
        assert "detached_from_slot_id" not in node.metadata

    bound = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": replacement.id,
            "product": {"id": "rebound-1", "display_name": "AÇÚCAR 5KG", "price": "18,90", "unit": "UN"},
        }
    )
    assert bound.ok and bound.changed
    assert session.page.node(bindings["name"]).text == "AÇÚCAR 5KG"
    assert session.page.node(bindings["price_complete"]).text == "18,90"


def test_catalog_image_update_cascades_to_all_bound_cards_and_undo_restores_sources():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    product = {
        "id": "img-1",
        "display_name": "CAFÉ 500G",
        "price": "19,90",
        "unit": "UN",
        "image_path": "cafe-original.png",
    }
    session.document.metadata["products"] = [dict(product)]

    first_page_id = session.page.id
    first = router.dispatch({"name": "create_product_card", "include_image": True})
    first_slot = str(first.payload["slot_id"])
    assert router.dispatch({"name": "bind_product", "slot_id": first_slot, "product": product}).ok

    second_page_id = session.add_page(name="Página imagem 2")
    second = router.dispatch({"name": "create_product_card", "include_image": True})
    second_slot = str(second.payload["slot_id"])
    assert router.dispatch({"name": "bind_product", "slot_id": second_slot, "product": product}).ok

    updated = router.dispatch(
        {
            "name": "update_product_data",
            "product_id": "img-1",
            "changes": {"image_path": "cafe-atualizado.png"},
        }
    )

    assert updated.ok and updated.changed
    assert updated.payload["slots_updated"] == 2
    first_page = session.document.page(first_page_id)
    second_page = session.document.page(second_page_id)
    first_image = first_page.node(first_page.slots[first_slot].node_by_role["image"])
    second_image = second_page.node(second_page.slots[second_slot].node_by_role["image"])
    assert first_image.metadata["bound_image_source"] == "cafe-atualizado.png"
    assert second_image.metadata["bound_image_source"] == "cafe-atualizado.png"
    assert first_image.visible and second_image.visible

    assert session.undo() is True
    first_page = session.document.page(first_page_id)
    second_page = session.document.page(second_page_id)
    first_image = first_page.node(first_page.slots[first_slot].node_by_role["image"])
    second_image = second_page.node(second_page.slots[second_slot].node_by_role["image"])
    assert first_image.metadata["bound_image_source"] == "cafe-original.png"
    assert second_image.metadata["bound_image_source"] == "cafe-original.png"
