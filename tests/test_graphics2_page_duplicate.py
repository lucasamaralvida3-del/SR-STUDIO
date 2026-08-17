from __future__ import annotations

from srstudio.graphics2 import BindingRole, GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, Transform
from srstudio.graphics2.preflight import assert_document_integrity
from srstudio.graphics2.semantic_blocks import build_semantic_blocks


def _semantic_page(session: GraphicsSession):
    page = session.page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Card",
        transform=Transform(x=40, y=80, width=420, height=500),
    )
    page.add_node(group)

    bindings = {}
    specs = [
        (BindingRole.NAME, "ARROZ 5KG", 80, 120, 300, 50),
        (BindingRole.CURRENCY, "R$", 80, 300, 45, 40),
        (BindingRole.PRICE_REAIS, "24", 125, 275, 100, 80),
        (BindingRole.PRICE_CENTS, ",90", 225, 285, 75, 45),
        (BindingRole.UNIT, "/UN", 230, 335, 70, 30),
    ]
    for role, text, x, y, width, height in specs:
        node = GraphicsNode(
            kind=NodeKind.TEXT,
            name=role.value,
            text=text,
            transform=Transform(x=x, y=y, width=width, height=height),
            binding_role=role,
        )
        page.add_node(node, parent_id=group.id)
        bindings[role] = node.id

    slot = session.create_slot("Produto 1", bindings)
    session.bind_product(slot.id, {"id": "arroz", "display_name": "ARROZ 5KG", "price": "24,90", "unit": "UN"})
    build_semantic_blocks(session.document)
    return group, slot


def test_duplicate_page_gets_fresh_internal_identities_and_preserves_links():
    session = GraphicsSession(GraphicsDocument(name="Encarte"))
    source_group, source_slot = _semantic_page(session)
    source = session.page

    source_node_ids = set(source.nodes)
    source_slot_ids = set(source.slots)
    source_block_ids = set((source.metadata.get("semantic_blocks") or {}).keys())

    duplicate_id = session.add_page(duplicate_active=True)
    duplicate = session.page

    assert duplicate.id == duplicate_id
    assert duplicate.id != source.id
    assert set(duplicate.nodes).isdisjoint(source_node_ids)
    assert set(duplicate.slots).isdisjoint(source_slot_ids)

    duplicate_block_ids = set((duplicate.metadata.get("semantic_blocks") or {}).keys())
    assert duplicate_block_ids
    assert duplicate_block_ids.isdisjoint(source_block_ids)

    assert len(duplicate.nodes) == len(source.nodes)
    assert len(duplicate.slots) == len(source.slots)
    assert len(duplicate_block_ids) == len(source_block_ids)

    duplicate_slot = next(iter(duplicate.slots.values()))
    assert duplicate_slot.id != source_slot.id
    assert duplicate_slot.page_id == duplicate.id
    assert set(duplicate_slot.node_by_role.values()).issubset(set(duplicate.nodes))
    assert not set(duplicate_slot.node_by_role.values()).intersection(source_node_ids)

    duplicate_group = next(node for node in duplicate.nodes.values() if node.kind is NodeKind.GROUP)
    assert duplicate_group.id != source_group.id
    assert duplicate_group.children
    for child_id in duplicate_group.children:
        child = duplicate.nodes[child_id]
        assert child.parent_id == duplicate_group.id
        assert child_id not in source_node_ids

    blocks = duplicate.metadata["semantic_blocks"]
    for block_id, block in blocks.items():
        assert block["id"] == block_id
        assert set(block.get("members") or []).issubset(set(duplicate.nodes))
        if block.get("slot_id"):
            assert block["slot_id"] in duplicate.slots
        for ids in (block.get("roles") or {}).values():
            assert set(ids).issubset(set(duplicate.nodes))
        assert set((block.get("template_geometry") or {}).keys()).issubset(set(duplicate.nodes))

    for node in duplicate.nodes.values():
        semantic_price = str(node.metadata.get("semantic_price_block_id") or "")
        semantic_card = str(node.metadata.get("semantic_product_card_id") or "")
        if semantic_price:
            assert semantic_price in blocks
        if semantic_card:
            assert semantic_card in blocks

    assert_document_integrity(session.document)


def test_duplicate_page_can_be_rebuilt_semantically_without_collisions():
    session = GraphicsSession(GraphicsDocument(name="Encarte"))
    _semantic_page(session)
    session.add_page(duplicate_active=True)

    build_semantic_blocks(session.document)
    assert_document_integrity(session.document)

    page_ids = {page.id for page in session.document.pages}
    assert len(page_ids) == 2

    all_node_ids = [node_id for page in session.document.pages for node_id in page.nodes]
    all_slot_ids = [slot_id for page in session.document.pages for slot_id in page.slots]
    assert len(all_node_ids) == len(set(all_node_ids))
    assert len(all_slot_ids) == len(set(all_slot_ids))

    for page in session.document.pages:
        blocks = page.metadata.get("semantic_blocks") or {}
        assert blocks
        for slot in page.slots.values():
            assert slot.page_id == page.id
            assert set(slot.node_by_role.values()).issubset(set(page.nodes))
