from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks, semantic_block


def _locked_text(name: str, text: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": 40},
        metadata={"source_name": name},
    )


def _card_document() -> tuple[GraphicsDocument, GraphicsNode, GraphicsNode]:
    document = GraphicsDocument(name="Duplicação de ProductCard")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group Product 42",
        transform=Transform(x=100, y=100, width=420, height=330),
        metadata={
            "source": "pptx-group",
            "source_name": "Group Product 42",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    name = _locked_text("Product Name", "LINGUIÇA MISTA CASEIRA SR", 145, 125, 300, 55)
    currency = _locked_text("Currency", "R$", 255, 300, 45, 55)
    whole = _locked_text("Whole", "25", 300, 260, 125, 120)
    cents = _locked_text("Cents", ",77", 425, 270, 48, 45)
    unit = _locked_text("Unit", "KG", 425, 330, 48, 42)
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Picture 1",
        locked=True,
        transform=Transform(x=135, y=180, width=230, height=170),
        metadata={"source_name": "Picture 1"},
    )
    for node in (name, image, currency, whole, cents, unit):
        page.add_node(node, parent_id=group.id)
    document.metadata["products"] = [
        {
            "id": "p-original",
            "display_name": "LINGUIÇA MISTA CASEIRA SR",
            "price": "25,77",
            "unit": "KG",
            "image_path": "/tmp/linguica.png",
        },
        {
            "id": "p-copy",
            "display_name": "COSTELINHA SUÍNA TIPO 01",
            "price": "28,66",
            "unit": "KG",
            "image_path": "/tmp/costelinha.png",
        },
    ]
    return document, group, name


def test_duplicate_recovered_product_card_clones_semantics_and_keeps_binding_isolated():
    document, group, name = _card_document()
    page = document.active_page
    build_semantic_blocks(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    original_slot_id = next(iter(page.slots))
    original_slot = page.slots[original_slot_id]

    first_bind = router.dispatch({"name": "bind_product", "slot_id": original_slot_id, "product_id": "p-original"})
    assert first_bind.ok and first_bind.changed

    selected = router.dispatch({"name": "select", "node_id": name.id, "semantic": True, "semantic_scope": "card"})
    assert selected.ok
    assert router.session.selection == {group.id}

    duplicated = router.dispatch({"name": "duplicate", "dx": 450, "dy": 0})
    assert duplicated.ok and duplicated.changed
    assert len(duplicated.payload["node_ids"]) == 1
    assert len(duplicated.payload["slot_ids"]) == 1

    page = router.session.page
    clone_group_id = duplicated.payload["node_ids"][0]
    clone_slot_id = duplicated.payload["slot_ids"][0]
    clone_group = page.node(clone_group_id)
    clone_slot = page.slots[clone_slot_id]
    assert clone_group is not None
    assert clone_group.transform.x == group.transform.x + 450
    assert clone_slot_id != original_slot_id
    assert clone_slot.metadata["semantic_recovered"] is False
    assert clone_slot.metadata["duplicated_from_slot_id"] == original_slot_id
    assert clone_slot.product_id == "p-original"
    assert set(clone_slot.node_by_role.values()).isdisjoint(set(original_slot.node_by_role.values()))

    clone_card_id = clone_slot.metadata["semantic_product_card_id"]
    clone_card = semantic_block(page, clone_card_id)
    assert clone_card is not None
    assert clone_card["members"] == [clone_group_id]
    assert clone_card_id != original_slot.metadata["semantic_product_card_id"]

    clone_name_id = clone_slot.node_by_role[BindingRole.NAME.value]
    clone_name = page.node(clone_name_id)
    assert clone_name is not None
    selected_clone = router.dispatch({"name": "select", "node_id": clone_name_id, "semantic": True})
    assert selected_clone.ok
    assert selected_clone.payload["semantic_kind"] == "product_card"
    assert router.session.selection == {clone_group_id}

    bind_copy = router.dispatch({"name": "bind_product", "slot_id": clone_slot_id, "product_id": "p-copy"})
    assert bind_copy.ok and bind_copy.changed
    page = router.session.page
    assert page.node(clone_name_id).text == "COSTELINHA SUÍNA TIPO 01"
    assert page.node(original_slot.node_by_role[BindingRole.NAME.value]).text == "LINGUIÇA MISTA CASEIRA SR"
    assert page.slots[clone_slot_id].product_id == "p-copy"
    assert page.slots[original_slot_id].product_id == "p-original"

    assert router.dispatch({"name": "undo"}).changed
    page = router.session.page
    assert page.slots[clone_slot_id].product_id == "p-original"
    assert page.node(clone_name_id).text == "LINGUIÇA MISTA CASEIRA SR"
    assert router.dispatch({"name": "redo"}).changed
    page = router.session.page
    assert page.slots[clone_slot_id].product_id == "p-copy"
    assert page.node(clone_name_id).text == "COSTELINHA SUÍNA TIPO 01"


def test_duplicate_product_card_is_one_atomic_undo_redo_operation():
    document, group, name = _card_document()
    build_semantic_blocks(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    original_node_count = len(router.session.page.nodes)
    original_slot_count = len(router.session.page.slots)

    router.dispatch({"name": "select", "node_id": name.id, "semantic": True, "semantic_scope": "card"})
    duplicated = router.dispatch({"name": "duplicate", "dx": 40, "dy": 30})
    assert duplicated.changed
    clone_group_id = duplicated.payload["node_ids"][0]
    clone_slot_id = duplicated.payload["slot_ids"][0]
    assert len(router.session.page.nodes) > original_node_count
    assert len(router.session.page.slots) == original_slot_count + 1

    assert router.dispatch({"name": "undo"}).changed
    assert len(router.session.page.nodes) == original_node_count
    assert len(router.session.page.slots) == original_slot_count
    assert router.session.page.node(clone_group_id) is None
    assert clone_slot_id not in router.session.page.slots

    assert router.dispatch({"name": "redo"}).changed
    assert len(router.session.page.nodes) > original_node_count
    assert len(router.session.page.slots) == original_slot_count + 1
    assert router.session.page.node(clone_group_id) is not None
    assert clone_slot_id in router.session.page.slots
