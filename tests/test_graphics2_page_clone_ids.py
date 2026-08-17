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


def _semantic_document() -> GraphicsDocument:
    document = GraphicsDocument(name="Página semântica")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group Product 9",
        transform=Transform(x=100, y=100, width=420, height=330),
        metadata={
            "source": "pptx-group",
            "source_name": "Group Product 9",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    for node in (
        _text("Product Name", "ARROZ PATOSUL 5KG", 145, 125, 300, 55),
        GraphicsNode(kind=NodeKind.IMAGE, name="Picture 1", locked=True, transform=Transform(x=135, y=180, width=230, height=170), metadata={"source_name": "Picture 1"}),
        _text("Currency", "R$", 255, 300, 45, 55),
        _text("Whole", "25", 300, 260, 125, 120),
        _text("Cents", ",77", 425, 270, 48, 45),
        _text("Unit", "UN", 425, 330, 48, 42),
    ):
        page.add_node(node, parent_id=group.id)
    build_semantic_blocks(document)
    return document


def test_duplicate_page_remaps_nodes_slots_and_semantic_blocks_without_collisions():
    document = _semantic_document()
    original = document.active_page
    original_node_ids = set(original.nodes)
    original_slot_ids = set(original.slots)
    original_block_ids = set((original.metadata.get("semantic_blocks") or {}).keys())
    router = GraphicsCommandRouter(GraphicsSession(document))

    result = router.dispatch({"name": "duplicate_page", "name_value": "Página 2"})

    assert result.ok and result.changed
    clone = router.session.page
    assert clone.id != original.id
    assert clone.name == "Página 2"
    assert set(clone.nodes).isdisjoint(original_node_ids)
    assert set(clone.slots).isdisjoint(original_slot_ids)
    assert set((clone.metadata.get("semantic_blocks") or {}).keys()).isdisjoint(original_block_ids)

    all_page_ids = [page.id for page in router.session.document.pages]
    all_node_ids = [node_id for page in router.session.document.pages for node_id in page.nodes]
    all_slot_ids = [slot_id for page in router.session.document.pages for slot_id in page.slots]
    all_block_ids = [block_id for page in router.session.document.pages for block_id in (page.metadata.get("semantic_blocks") or {})]
    assert len(all_page_ids) == len(set(all_page_ids))
    assert len(all_node_ids) == len(set(all_node_ids))
    assert len(all_slot_ids) == len(set(all_slot_ids))
    assert len(all_block_ids) == len(set(all_block_ids))

    surviving_node_ids = set(clone.nodes)
    for slot in clone.slots.values():
        assert slot.page_id == clone.id
        assert set(slot.node_by_role.values()).issubset(surviving_node_ids)
        product_card_id = slot.metadata.get("semantic_product_card_id")
        if product_card_id:
            assert product_card_id in clone.metadata["semantic_blocks"]
        for price_id in slot.metadata.get("semantic_price_block_ids") or []:
            assert price_id in clone.metadata["semantic_blocks"]

    for block_id, block in clone.metadata["semantic_blocks"].items():
        assert block["id"] == block_id
        assert block.get("slot_id") in clone.slots
        assert set(block.get("members") or []).issubset(surviving_node_ids)
        for node_ids in (block.get("roles") or {}).values():
            assert set(node_ids).issubset(surviving_node_ids)


def test_duplicate_page_is_atomic_for_undo_redo_and_keeps_unique_ids():
    router = GraphicsCommandRouter(GraphicsSession(_semantic_document()))
    original_page_id = router.session.page.id

    duplicated = router.dispatch({"name": "duplicate_page"})
    clone_page_id = duplicated.payload["page_id"]
    assert len(router.session.document.pages) == 2
    assert clone_page_id != original_page_id

    assert router.dispatch({"name": "undo"}).changed
    assert len(router.session.document.pages) == 1
    assert router.session.document.active_page_id == original_page_id

    assert router.dispatch({"name": "redo"}).changed
    assert len(router.session.document.pages) == 2
    assert router.session.document.page(clone_page_id) is not None
