from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks, semantic_block


def _text(name: str, text: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": 40},
        metadata={"source_name": name},
    )


def _semantic_router() -> tuple[GraphicsCommandRouter, str, str]:
    document = GraphicsDocument(name="Clipboard G2")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group Product 7",
        transform=Transform(x=100, y=100, width=420, height=330),
        metadata={
            "source": "pptx-group",
            "source_name": "Group Product 7",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    name = _text("Product Name", "ARROZ PATOSUL 5KG", 145, 125, 300, 55)
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Picture 1",
        locked=True,
        transform=Transform(x=135, y=180, width=230, height=170),
        metadata={"source_name": "Picture 1"},
    )
    currency = _text("Currency", "R$", 255, 300, 45, 55)
    whole = _text("Whole", "25", 300, 260, 125, 120)
    cents = _text("Cents", ",77", 425, 270, 48, 45)
    unit = _text("Unit", "UN", 425, 330, 48, 42)
    for node in (name, image, currency, whole, cents, unit):
        page.add_node(node, parent_id=group.id)
    document.metadata["products"] = [
        {
            "id": "p1",
            "display_name": "ARROZ PATOSUL 5KG",
            "price": "25,77",
            "unit": "UN",
            "image_path": "/tmp/arroz.png",
        },
        {
            "id": "p2",
            "display_name": "ACUCAR DELTA 5KG",
            "price": "18,66",
            "unit": "UN",
            "image_path": "/tmp/acucar.png",
        },
    ]
    build_semantic_blocks(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    slot_id = next(iter(page.slots))
    assert router.dispatch({"name": "bind_product", "slot_id": slot_id, "product_id": "p1"}).changed
    return router, group.id, name.id


def test_copy_paste_product_card_to_another_page_preserves_semantics_and_binding_isolation():
    router, group_id, name_id = _semantic_router()
    source_page = router.session.page
    source_slot_id = next(iter(source_page.slots))
    source_slot = source_page.slots[source_slot_id]

    selected = router.dispatch({"name": "select", "node_id": name_id, "semantic": True, "semantic_scope": "card"})
    assert selected.ok
    assert router.session.selection == {group_id}

    copied = router.dispatch({"name": "copy"})
    assert copied.ok and not copied.changed
    assert copied.payload["count"] == len(source_page.nodes)
    assert router.payload()["editor"]["clipboard_available"] is True

    added = router.dispatch({"name": "add_page", "name_value": "Página destino"})
    assert added.changed
    destination_page = router.session.page
    assert not destination_page.nodes
    assert not destination_page.slots

    pasted = router.dispatch({"name": "paste", "dx": 30, "dy": 40})
    assert pasted.ok and pasted.changed
    assert len(pasted.payload["node_ids"]) == 1
    assert len(pasted.payload["slot_ids"]) == 1

    clone_group_id = pasted.payload["node_ids"][0]
    clone_slot_id = pasted.payload["slot_ids"][0]
    clone_group = destination_page.node(clone_group_id)
    clone_slot = destination_page.slots[clone_slot_id]
    assert clone_group is not None
    assert clone_group.transform.x == 130
    assert clone_group.transform.y == 140
    assert clone_slot.page_id == destination_page.id
    assert clone_slot.product_id == "p1"
    assert set(clone_slot.node_by_role.values()).isdisjoint(set(source_slot.node_by_role.values()))

    clone_card_id = clone_slot.metadata["semantic_product_card_id"]
    clone_card = semantic_block(destination_page, clone_card_id)
    assert clone_card is not None
    assert clone_card["kind"] == "product_card"
    assert clone_card["members"] == [clone_group_id]
    assert clone_slot.metadata["semantic_price_block_ids"]

    clone_name_id = clone_slot.node_by_role[BindingRole.NAME.value]
    selected_clone = router.dispatch({"name": "select", "node_id": clone_name_id, "semantic": True})
    assert selected_clone.payload["semantic_kind"] == "product_card"
    assert router.session.selection == {clone_group_id}

    rebound = router.dispatch({"name": "bind_product", "slot_id": clone_slot_id, "product_id": "p2"})
    assert rebound.ok and rebound.changed
    assert destination_page.node(clone_name_id).text == "ACUCAR DELTA 5KG"
    assert source_page.node(source_slot.node_by_role[BindingRole.NAME.value]).text == "ARROZ PATOSUL 5KG"
    assert source_page.slots[source_slot_id].product_id == "p1"
    assert destination_page.slots[clone_slot_id].product_id == "p2"


def test_paste_is_one_atomic_undo_redo_and_clipboard_survives_history():
    router, group_id, name_id = _semantic_router()
    router.dispatch({"name": "select", "node_id": name_id, "semantic": True, "semantic_scope": "card"})
    copied = router.dispatch({"name": "copy"})
    assert copied.ok
    original_node_count = len(router.session.page.nodes)
    original_slot_count = len(router.session.page.slots)

    pasted = router.dispatch({"name": "paste", "dx": 50, "dy": 20})
    clone_group_id = pasted.payload["node_ids"][0]
    clone_slot_id = pasted.payload["slot_ids"][0]
    assert len(router.session.page.nodes) > original_node_count
    assert len(router.session.page.slots) == original_slot_count + 1

    assert router.dispatch({"name": "undo"}).changed
    assert len(router.session.page.nodes) == original_node_count
    assert len(router.session.page.slots) == original_slot_count
    assert router.session.page.node(clone_group_id) is None
    assert clone_slot_id not in router.session.page.slots
    assert router.payload()["editor"]["clipboard_available"] is True

    assert router.dispatch({"name": "redo"}).changed
    assert router.session.page.node(clone_group_id) is not None
    assert clone_slot_id in router.session.page.slots

    assert router.dispatch({"name": "undo"}).changed
    second_paste = router.dispatch({"name": "paste", "dx": 80, "dy": 60})
    assert second_paste.changed
    assert second_paste.payload["node_ids"][0] != clone_group_id


def test_copy_paste_plain_multiselection_uses_fresh_ids_and_preserves_geometry():
    document = GraphicsDocument(name="Clipboard simples")
    page = document.active_page
    a = GraphicsNode(kind=NodeKind.RECT, name="A", transform=Transform(x=10, y=20, width=100, height=80))
    b = GraphicsNode(kind=NodeKind.TEXT, name="B", text="OFERTA", transform=Transform(x=200, y=220, width=120, height=50))
    page.add_node(a)
    page.add_node(b)
    router = GraphicsCommandRouter(GraphicsSession(document))
    router.dispatch({"name": "select", "node_id": a.id})
    router.dispatch({"name": "select", "node_id": b.id, "additive": True})

    assert router.dispatch({"name": "copy"}).payload["count"] == 2
    pasted = router.dispatch({"name": "paste", "dx": 15, "dy": 25})

    assert pasted.changed
    assert len(pasted.payload["node_ids"]) == 2
    clones = [router.session.page.node(node_id) for node_id in pasted.payload["node_ids"]]
    assert all(node is not None for node in clones)
    clone_by_name = {node.name: node for node in clones if node is not None}
    assert clone_by_name["A"].id != a.id
    assert clone_by_name["A"].transform.x == 25
    assert clone_by_name["A"].transform.y == 45
    assert clone_by_name["B"].id != b.id
    assert clone_by_name["B"].transform.x == 215
    assert clone_by_name["B"].transform.y == 245
