from __future__ import annotations

from srstudio.graphics2 import GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, Transform
from srstudio.graphics2.semantic_blocks import build_semantic_blocks
from srstudio.graphics2.usability_gate import inspect_encarte_usability


def _text(name: str, text: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": 36},
        metadata={"source_name": name},
    )


def _recovered_group_document() -> GraphicsDocument:
    document = GraphicsDocument(name="Encarte recuperado multipágina")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group 42",
        transform=Transform(x=100, y=100, width=420, height=360),
        metadata={
            "source": "pptx-group",
            "source_name": "Group 42",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    nodes = [
        _text("Name", "LINGUIÇA MISTA CASEIRA SR", 135, 125, 300, 60),
        GraphicsNode(
            kind=NodeKind.IMAGE,
            name="Product Image",
            locked=True,
            transform=Transform(x=140, y=190, width=220, height=160),
            metadata={"source_name": "Product Image"},
        ),
        _text("Currency", "R$", 245, 330, 45, 50),
        _text("Whole", "25", 290, 290, 120, 110),
        _text("Cents", ",77", 410, 300, 55, 45),
        _text("Unit", "KG", 410, 355, 55, 40),
    ]
    for node in nodes:
        page.add_node(node, parent_id=group.id)
    return document


def test_recovered_slots_are_unique_across_duplicate_pages_and_stable_on_rebuild():
    document = _recovered_group_document()
    build_semantic_blocks(document)
    session = GraphicsSession(document)

    first_slot = next(iter(session.page.slots.values()))
    session.bind_product(
        first_slot.id,
        {
            "id": "produto-a",
            "display_name": "ACÉM BOVINO",
            "price": "31,50",
            "unit": "KG",
            "image_path": "C:/produtos/acem.png",
        },
    )

    session.add_page(duplicate_active=True)
    second_slot = next(iter(session.page.slots.values()))
    session.bind_product(
        second_slot.id,
        {
            "id": "produto-b",
            "display_name": "COSTELA RIPA",
            "price": "33,64",
            "unit": "KG",
            "image_path": "C:/produtos/costela.png",
        },
    )

    build_semantic_blocks(document)

    slot_ids = [slot.id for page in document.pages for slot in page.slots.values()]
    assert len(slot_ids) == 2
    assert len(set(slot_ids)) == 2
    assert all(":page-" in slot_id for slot_id in slot_ids)

    products = [next(iter(page.slots.values())).product_id for page in document.pages]
    assert products == ["produto-a", "produto-b"]
    snapshots = [next(iter(page.slots.values())).metadata["product_snapshot"] for page in document.pages]
    assert [snapshot["id"] for snapshot in snapshots] == ["produto-a", "produto-b"]

    block_ids = [
        block_id
        for page in document.pages
        for block_id in (page.metadata.get("semantic_blocks") or {})
    ]
    assert len(block_ids) == len(set(block_ids))

    first_pass_ids = [list(page.slots) for page in document.pages]
    build_semantic_blocks(document)
    second_pass_ids = [list(page.slots) for page in document.pages]
    assert second_pass_ids == first_pass_ids
    assert [next(iter(page.slots.values())).product_id for page in document.pages] == ["produto-a", "produto-b"]

    report = inspect_encarte_usability(document, require_bound_product=True)
    assert report.ready is True
    assert report.metrics["duplicate_slot_ids"] == 0
    assert report.metrics["duplicate_node_ids"] == 0


def test_single_page_recovered_slot_keeps_legacy_stable_id():
    document = _recovered_group_document()

    build_semantic_blocks(document)
    first_id = next(iter(document.active_page.slots))
    build_semantic_blocks(document)
    second_id = next(iter(document.active_page.slots))

    assert first_id == second_id == "slot:recovered:group-42"
