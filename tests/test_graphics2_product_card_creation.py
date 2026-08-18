from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsDocument, GraphicsSession, NodeKind
from srstudio.graphics2.preflight import run_preflight


def _node_for_role(session: GraphicsSession, slot_id: str, role: str):
    slot = session.page.slots[slot_id]
    node_id = slot.node_by_role.get(role)
    if node_id:
        return session.page.node(node_id)
    extras = dict(slot.metadata.get("extra_bindings") or {})
    ids = list(extras.get(role) or [])
    return session.page.node(ids[0]) if ids else None


def test_create_product_card_command_builds_semantic_card_and_three_price_blocks():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)

    result = router.dispatch(
        {
            "name": "create_product_card",
            "x": 100,
            "y": 120,
            "width": 460,
            "height": 400,
            "product_name": "ARROZ 5KG",
            "include_description": True,
            "include_image": True,
            "include_quantity": True,
            "include_validity": True,
            "include_app_price": True,
            "include_wholesale": True,
        }
    )

    assert result.ok is True and result.changed is True
    slot_id = str(result.payload["slot_id"])
    card_id = str(result.payload["product_card_id"])
    slot = session.page.slots[slot_id]
    card = session.page.metadata["semantic_blocks"][card_id]

    assert slot.metadata["source"] == "g2-product-card"
    assert card["kind"] == "product_card"
    assert card["slot_id"] == slot_id
    assert _node_for_role(session, slot_id, "name").text == "ARROZ 5KG"
    assert _node_for_role(session, slot_id, "image").kind is NodeKind.IMAGE
    assert _node_for_role(session, slot_id, "description").id in card["members"]
    assert _node_for_role(session, slot_id, "validity").id in card["members"]

    price_blocks = [
        block
        for block in session.page.metadata["semantic_blocks"].values()
        if block["kind"] == "price_block" and block["slot_id"] == slot_id
    ]
    assert len(price_blocks) == 3
    assert len(card["metadata"]["price_blocks"]) == 3
    assert any(block["metadata"].get("commercial_role") == "wholesale" for block in price_blocks)
    assert not [issue for issue in run_preflight(session.document) if issue.severity == "error"]


def test_product_card_bind_and_replace_updates_all_fields_without_moving_layout():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch(
        {
            "name": "create_product_card",
            "include_description": True,
            "include_image": True,
            "include_quantity": True,
            "include_validity": True,
            "include_app_price": True,
            "include_wholesale": True,
        }
    )
    slot_id = str(created.payload["slot_id"])
    slot = session.page.slots[slot_id]
    bound_ids = set(slot.node_by_role.values())
    for ids in dict(slot.metadata.get("extra_bindings") or {}).values():
        bound_ids.update(ids)
    before_geometry = {
        node_id: deepcopy(session.page.node(node_id).transform)
        for node_id in bound_ids
        if session.page.node(node_id) is not None
    }

    first = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot_id,
            "product": {
                "id": "p1",
                "display_name": "CAFÉ PREMIUM 500G",
                "description": "TORRA MÉDIA",
                "price": "19.90",
                "retail_price": "19.90",
                "app_price": "17.49",
                "wholesale_price": "16.89",
                "quantity": "6",
                "unit": "UN",
                "validity": "20/08/2026",
                "image_path": "produto-cafe.png",
            },
        }
    )

    assert first.ok is True and first.changed is True
    assert _node_for_role(session, slot_id, "name").text == "CAFÉ PREMIUM 500G"
    assert _node_for_role(session, slot_id, "description").text == "TORRA MÉDIA"
    assert _node_for_role(session, slot_id, "price_currency").text == "R$"
    assert _node_for_role(session, slot_id, "price_complete").text == "19,90"
    assert _node_for_role(session, slot_id, "app_price_complete").text == "17,49"
    assert _node_for_role(session, slot_id, "wholesale_price").text == "16,89"
    assert _node_for_role(session, slot_id, "wholesale_price_currency").text == "R$"
    assert _node_for_role(session, slot_id, "quantity").text == "6"
    assert _node_for_role(session, slot_id, "unit").text == "/UN"
    assert _node_for_role(session, slot_id, "validity").text == "20/08/2026"
    image = _node_for_role(session, slot_id, "image")
    assert image.visible is True
    assert image.metadata["bound_image_source"] == "produto-cafe.png"

    second = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot_id,
            "product": {
                "id": "p2",
                "display_name": "CAFÉ TRADICIONAL 500G",
                "price": "18.75",
                "retail_price": "18.75",
                "unit": "UN",
            },
        }
    )

    assert second.ok is True and second.changed is True
    assert _node_for_role(session, slot_id, "name").text == "CAFÉ TRADICIONAL 500G"
    assert _node_for_role(session, slot_id, "price_complete").text == "18,75"
    for role in (
        "description",
        "app_price_complete",
        "app_price_currency",
        "wholesale_price",
        "wholesale_price_currency",
        "quantity",
        "validity",
    ):
        node = _node_for_role(session, slot_id, role)
        assert node.text == ""
        assert node.visible is False
    assert image.asset_id == ""
    assert image.visible is False

    for node_id, geometry in before_geometry.items():
        assert session.page.node(node_id).transform == geometry


def test_product_card_binding_is_noop_aware_and_undo_redo_safe():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch({"name": "create_product_card", "include_app_price": True})
    slot_id = str(created.payload["slot_id"])
    product = {
        "id": "p1",
        "display_name": "LEITE 1L",
        "price": "5,99",
        "app_price": "4,99",
        "unit": "UN",
    }

    first = router.dispatch({"name": "bind_product", "slot_id": slot_id, "product": product})
    second = router.dispatch({"name": "bind_product", "slot_id": slot_id, "product": deepcopy(product)})

    assert first.ok and first.changed
    assert second.ok and second.changed is False
    assert session.undo() is True
    # One undo reverts the first binding because the no-op did not push history.
    restored_slot = session.page.slots[slot_id]
    assert restored_slot.product_id == ""
    assert session.page.node(restored_slot.node_by_role["name"]).text == "Novo produto"
    assert session.redo() is True
    restored_slot = session.page.slots[slot_id]
    assert restored_slot.product_id == "p1"
    assert session.page.node(restored_slot.node_by_role["name"]).text == "LEITE 1L"


def test_rebind_command_rejects_missing_node_without_corrupting_slot():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch({"name": "create_product_card"})
    slot_id = str(created.payload["slot_id"])
    slot = session.page.slots[slot_id]
    before = deepcopy(slot.node_by_role)

    result = router.dispatch(
        {
            "name": "rebind_slot",
            "slot_id": slot_id,
            "bindings": {"name": "node-inexistente"},
        }
    )

    assert result.ok is False
    assert result.changed is False
    assert "KeyError" in result.message
    assert session.page.slots[slot_id].node_by_role == before


def test_remove_smart_slot_can_keep_or_delete_visual_nodes_and_supports_undo():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch({"name": "create_product_card", "include_app_price": True})
    slot_id = str(created.payload["slot_id"])
    slot = session.page.slots[slot_id]
    node_ids = set(slot.node_by_role.values())
    for ids in dict(slot.metadata.get("extra_bindings") or {}).values():
        node_ids.update(ids)

    removed = router.dispatch({"name": "remove_smart_slot", "slot_id": slot_id, "delete_nodes": False})
    assert removed.ok and removed.changed
    assert slot_id not in session.page.slots
    assert node_ids.issubset(session.page.nodes)
    assert not [
        block
        for block in session.page.metadata.get("semantic_blocks", {}).values()
        if block.get("slot_id") == slot_id
    ]

    assert session.undo() is True
    assert slot_id in session.page.slots
    assert session.redo() is True
    assert slot_id not in session.page.slots

    created2 = router.dispatch({"name": "create_product_card"})
    slot2_id = str(created2.payload["slot_id"])
    slot2 = session.page.slots[slot2_id]
    node2_ids = set(slot2.node_by_role.values())
    deleted = router.dispatch({"name": "remove_smart_slot", "slot_id": slot2_id, "delete_nodes": True})
    assert deleted.ok and deleted.changed
    assert slot2_id not in session.page.slots
    assert node2_ids.isdisjoint(session.page.nodes)


def test_two_created_product_cards_keep_state_isolated_and_round_trip_serializable():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    first = router.dispatch({"name": "create_product_card", "x": 30, "y": 30})
    second = router.dispatch({"name": "create_product_card", "x": 520, "y": 30})
    slot_a = str(first.payload["slot_id"])
    slot_b = str(second.payload["slot_id"])

    router.dispatch(
        {"name": "bind_product", "slot_id": slot_a, "product": {"id": "a", "name": "ARROZ", "price": "20,00"}}
    )
    router.dispatch(
        {"name": "bind_product", "slot_id": slot_b, "product": {"id": "b", "name": "FEIJÃO", "price": "8,00"}}
    )

    assert session.page.slots[slot_a].product_id == "a"
    assert session.page.slots[slot_b].product_id == "b"
    assert _node_for_role(session, slot_a, "name").text == "ARROZ"
    assert _node_for_role(session, slot_b, "name").text == "FEIJÃO"

    restored = GraphicsDocument.from_dict(session.document.to_dict())
    restored_session = GraphicsSession(restored)
    assert restored_session.page.slots[slot_a].product_id == "a"
    assert restored_session.page.slots[slot_b].product_id == "b"
    assert restored_session.page.slots[slot_a].metadata["product_snapshot"]["name"] == "ARROZ"
    assert restored_session.page.slots[slot_b].metadata["product_snapshot"]["name"] == "FEIJÃO"
    assert not [issue for issue in run_preflight(restored) if issue.severity == "error"]
