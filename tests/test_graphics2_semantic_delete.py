from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks


def _text(name: str, text: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        metadata={"source_name": name},
    )


def _router() -> tuple[GraphicsCommandRouter, str]:
    document = GraphicsDocument(name="Delete ProductCard")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group Product 3",
        transform=Transform(x=100, y=100, width=420, height=330),
        metadata={
            "source": "pptx-group",
            "source_name": "Group Product 3",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    children = [
        _text("Product Name", "FEIJAO VASCONCELOS 1KG", 145, 125, 300, 55),
        GraphicsNode(kind=NodeKind.IMAGE, name="Picture 1", locked=True, transform=Transform(x=135, y=180, width=230, height=170), metadata={"source_name": "Picture 1"}),
        _text("Currency", "R$", 255, 300, 45, 55),
        _text("Whole", "8", 300, 260, 125, 120),
        _text("Cents", ",99", 425, 270, 48, 45),
        _text("Unit", "UN", 425, 330, 48, 42),
    ]
    for node in children:
        page.add_node(node, parent_id=group.id)
    build_semantic_blocks(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    name_id = children[0].id
    return router, name_id


def test_delete_duplicated_product_card_removes_slot_and_semantic_blocks_atomically():
    router, name_id = _router()
    page = router.session.page
    original_slot_ids = set(page.slots)
    original_block_ids = set((page.metadata.get("semantic_blocks") or {}).keys())

    router.dispatch({"name": "select", "node_id": name_id, "semantic": True, "semantic_scope": "card"})
    duplicated = router.dispatch({"name": "duplicate", "dx": 450, "dy": 0})
    assert duplicated.changed
    clone_group_id = duplicated.payload["node_ids"][0]
    clone_slot_id = duplicated.payload["slot_ids"][0]
    page = router.session.page
    clone_slot = page.slots[clone_slot_id]
    clone_block_ids = {
        clone_slot.metadata["semantic_product_card_id"],
        *clone_slot.metadata["semantic_price_block_ids"],
    }
    assert clone_block_ids.issubset(set(page.metadata["semantic_blocks"]))

    router.dispatch({"name": "select", "node_id": clone_group_id, "semantic": True, "semantic_scope": "card"})
    deleted = router.dispatch({"name": "delete"})
    assert deleted.ok and deleted.changed

    page = router.session.page
    assert page.node(clone_group_id) is None
    assert clone_slot_id not in page.slots
    assert not clone_block_ids.intersection(set(page.metadata["semantic_blocks"]))
    assert original_slot_ids.issubset(set(page.slots))
    assert original_block_ids.issubset(set(page.metadata["semantic_blocks"]))

    assert router.dispatch({"name": "undo"}).changed
    page = router.session.page
    assert page.node(clone_group_id) is not None
    assert clone_slot_id in page.slots
    assert clone_block_ids.issubset(set(page.metadata["semantic_blocks"]))

    assert router.dispatch({"name": "redo"}).changed
    page = router.session.page
    assert page.node(clone_group_id) is None
    assert clone_slot_id not in page.slots
    assert not clone_block_ids.intersection(set(page.metadata["semantic_blocks"]))


def test_deleting_price_members_prunes_price_block_without_leaving_dead_node_references():
    router, name_id = _router()
    page = router.session.page
    slot_id = next(iter(page.slots))
    slot = page.slots[slot_id]
    price_block_ids = list(slot.metadata["semantic_price_block_ids"])
    assert price_block_ids
    price_id = price_block_ids[0]
    block = page.metadata["semantic_blocks"][price_id]
    price_members = list(block["members"])

    router.session.selection = set(price_members)
    router.session.anchor_id = price_members[0]
    assert router.dispatch({"name": "delete"}).changed

    page = router.session.page
    surviving_ids = set(page.nodes)
    assert price_id not in page.metadata["semantic_blocks"]
    assert price_id not in page.slots[slot_id].metadata["semantic_price_block_ids"]
    for current_slot in page.slots.values():
        assert set(current_slot.node_by_role.values()).issubset(surviving_ids)
    for semantic in page.metadata["semantic_blocks"].values():
        assert set(semantic.get("members") or []).issubset(surviving_ids)
        for node_ids in (semantic.get("roles") or {}).values():
            assert set(node_ids).issubset(surviving_ids)
