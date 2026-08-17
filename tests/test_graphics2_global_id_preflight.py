from __future__ import annotations

import copy

import pytest

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.preflight import assert_document_integrity, run_preflight


def test_preflight_rejects_cross_page_node_slot_and_semantic_id_collisions():
    document = GraphicsDocument(name="Colisão")
    first = document.active_page
    node = GraphicsNode(kind=NodeKind.TEXT, text="Oferta", transform=Transform(width=100, height=40))
    first.add_node(node)
    slot = SmartSlot(name="Produto", page_id=first.id, node_by_role={"name": node.id})
    first.slots[slot.id] = slot
    block_id = "productcard:shared"
    first.metadata["semantic_blocks"] = {
        block_id: {"id": block_id, "kind": "product_card", "slot_id": slot.id, "members": [node.id], "roles": {}}
    }

    second = copy.deepcopy(first)
    second.id = "page_second"
    second.name = "Página 2"
    for current_slot in second.slots.values():
        current_slot.page_id = second.id
    document.pages.append(second)

    issues = run_preflight(document)
    codes = {issue.code for issue in issues}
    assert "DUPLICATE_NODE_ID" in codes
    assert "DUPLICATE_SLOT_ID" in codes
    assert "DUPLICATE_SEMANTIC_ID" in codes
    with pytest.raises(ValueError, match="DUPLICATE_"):
        assert_document_integrity(document)
