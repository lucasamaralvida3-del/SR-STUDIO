from __future__ import annotations

from srstudio.graphics2 import (
    GraphicsCommandRouter,
    GraphicsDocument,
    GraphicsNode,
    GraphicsSession,
    NodeKind,
    Transform,
    build_semantic_blocks,
)


def _named_text(name: str, text: str, *, x: float, y: float, width: float, height: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        visible=True,
        transform=Transform(x=x, y=y, width=width, height=height),
        metadata={"source": "pptx", "source_name": name},
    )


def test_detached_g2_product_card_is_not_recovered_on_later_semantic_rebuild():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch(
        {
            "name": "create_product_card",
            "include_description": False,
            "include_image": False,
            "include_quantity": False,
        }
    )
    slot_id = str(created.payload["slot_id"])
    slot = session.page.slots[slot_id]
    node_ids = set(slot.node_by_role.values())
    visibility = {node_id: session.page.node(node_id).visible for node_id in node_ids}

    removed = router.dispatch({"name": "remove_smart_slot", "slot_id": slot_id, "delete_nodes": False})

    assert removed.ok and removed.changed
    assert session.page.slots == {}
    for node_id in node_ids:
        node = session.page.node(node_id)
        assert node is not None
        assert node.metadata["smart_slot_detached"] is True
        assert node.metadata["detached_from_slot_id"] == slot_id
        assert node.visible == visibility[node_id]

    build_semantic_blocks(session.document)

    assert session.page.slots == {}
    assert not [
        block
        for block in session.page.metadata.get("semantic_blocks", {}).values()
        if block.get("slot_id") == slot_id
    ]
    for node_id in node_ids:
        assert session.page.node(node_id).visible == visibility[node_id]


def test_detached_named_import_slot_does_not_reappear_from_explicit_or_complete_price_recovery():
    document = GraphicsDocument(name="Template nomeado")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    nodes = [
        _named_text("SR_PRODUTO", "CAFÉ 500G", x=120, y=260, width=700, height=100),
        _named_text("MOEDA", "R$", x=80, y=540, width=90, height=60),
        _named_text("SR_PRECO_VAREJO", "19,90", x=190, y=510, width=520, height=150),
        _named_text("SR_UNIDADE_VAREJO", "CADA", x=720, y=565, width=130, height=60),
    ]
    for node in nodes:
        page.add_node(node)

    build_semantic_blocks(document)
    assert len(page.slots) == 1
    slot_id = next(iter(page.slots))
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    removed = router.dispatch({"name": "remove_smart_slot", "slot_id": slot_id, "delete_nodes": False})

    assert removed.ok and removed.changed
    assert session.page.slots == {}
    assert all(node.visible for node in nodes)
    assert all(node.metadata.get("smart_slot_detached") is True for node in nodes)

    build_semantic_blocks(session.document)
    build_semantic_blocks(session.document)

    assert session.page.slots == {}
    assert all(node.visible for node in nodes)
    assert not [
        block
        for block in session.page.metadata.get("semantic_blocks", {}).values()
        if block.get("kind") in {"price_block", "product_card"}
    ]


def test_detached_marker_round_trips_with_visuals_but_without_slot():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch({"name": "create_product_card", "include_image": False})
    slot_id = str(created.payload["slot_id"])
    node_ids = set(session.page.slots[slot_id].node_by_role.values())
    router.dispatch({"name": "remove_smart_slot", "slot_id": slot_id, "delete_nodes": False})

    restored = GraphicsDocument.from_dict(session.document.to_dict())

    assert restored.active_page.slots == {}
    for node_id in node_ids:
        assert restored.active_page.node(node_id) is not None
        assert restored.active_page.node(node_id).metadata["smart_slot_detached"] is True

    build_semantic_blocks(restored)
    assert restored.active_page.slots == {}
