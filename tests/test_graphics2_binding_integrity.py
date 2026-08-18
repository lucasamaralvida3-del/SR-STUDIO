from __future__ import annotations

from srstudio.graphics2 import GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.preflight import run_preflight


def _node() -> GraphicsNode:
    return GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=120, height=40))


def _codes(document: GraphicsDocument) -> set[str]:
    return {issue.code for issue in run_preflight(document) if issue.severity == "error"}


def test_preflight_detects_missing_primary_and_extra_binding_nodes():
    document = GraphicsDocument()
    page = document.active_page
    name = _node()
    page.add_node(name)
    slot = SmartSlot(
        name="Produto quebrado",
        page_id=page.id,
        node_by_role={"name": name.id, "retail_price": "node-primary-missing"},
        metadata={"extra_bindings": {"app_price_complete": ["node-extra-missing"]}},
    )
    page.slots[slot.id] = slot

    codes = _codes(document)

    assert "SLOT_NODE_MISSING" in codes
    assert "SLOT_EXTRA_NODE_MISSING" in codes


def test_preflight_detects_slot_page_mismatch_and_invalid_extra_shape():
    document = GraphicsDocument()
    page = document.active_page
    node = _node()
    page.add_node(node)
    slot = SmartSlot(
        name="Produto",
        page_id="pagina-errada",
        node_by_role={"name": node.id},
        metadata={"extra_bindings": [node.id]},
    )
    page.slots[slot.id] = slot

    codes = _codes(document)

    assert "SLOT_PAGE_MISMATCH" in codes
    assert "SLOT_EXTRA_BINDINGS_INVALID" in codes


def test_remove_node_cleans_extra_bindings_before_next_preflight():
    document = GraphicsDocument()
    page = document.active_page
    name = _node()
    app_price = _node()
    page.add_node(name)
    page.add_node(app_price)
    slot = SmartSlot(
        name="Produto",
        page_id=page.id,
        node_by_role={"name": name.id},
        metadata={
            "extra_bindings": {"app_price_complete": [app_price.id]},
            "secondary_price_node_id": app_price.id,
        },
    )
    page.slots[slot.id] = slot

    assert "SLOT_EXTRA_NODE_MISSING" not in _codes(document)
    page.remove_node(app_price.id)

    assert slot.metadata.get("extra_bindings") in (None, {})
    assert slot.metadata["secondary_price_node_id"] == ""
    assert "SLOT_EXTRA_NODE_MISSING" not in _codes(document)


def test_empty_slot_without_bindings_remains_valid():
    document = GraphicsDocument()
    page = document.active_page
    slot = SmartSlot(name="Slot vazio", page_id=page.id)
    page.slots[slot.id] = slot

    assert not _codes(document)
