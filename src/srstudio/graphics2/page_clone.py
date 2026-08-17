from __future__ import annotations

"""Safe page duplication for SR Graphics Engine 2.

A duplicated flyer page must be an independent editable scene. Reusing node
or SmartSlot ids works while pages are isolated, but it creates ambiguous
references for editor state, semantic blocks, saved merges and future commands.
This module clones a page with fresh identity while preserving visual geometry,
assets and product snapshots.
"""

from copy import deepcopy
from typing import Any, TYPE_CHECKING

from .model import GraphicsDocument, GraphicsPage, _id
from .semantic_blocks import build_semantic_blocks

if TYPE_CHECKING:
    from .operations import GraphicsSession


_SEMANTIC_NODE_METADATA_KEYS = {
    "semantic_price_block_id",
    "semantic_price_role",
    "semantic_product_card_id",
    "semantic_recovered_editable",
    "semantic_source_locked",
}
_SEMANTIC_NODE_STYLE_KEYS = {
    "semantic_price_role",
    "semantic_price_block_id",
    "semantic_fit_policy",
}
_SEMANTIC_SLOT_METADATA_KEYS = {
    "semantic_product_card_id",
    "semantic_price_block_ids",
    "smart_slot_id",
}


def _remap_exact_references(value: Any, mapping: dict[str, str]) -> Any:
    """Recursively remap exact id references without rewriting arbitrary text."""
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_remap_exact_references(item, mapping) for item in value]
    if isinstance(value, tuple):
        return tuple(_remap_exact_references(item, mapping) for item in value)
    if isinstance(value, dict):
        return {
            key: _remap_exact_references(item, mapping)
            for key, item in value.items()
        }
    return value


def clone_page_with_fresh_ids(
    source: GraphicsPage,
    *,
    name: str | None = None,
    rebuild_semantics: bool = True,
) -> GraphicsPage:
    """Return a visually identical page with independent scene identities.

    Asset ids intentionally remain shared because assets belong to the document.
    Page, node and SmartSlot ids are regenerated. Semantic block ids are
    rebuilt from the cloned slots/nodes so a command on the copy can never
    address the source page by accident.
    """

    page = deepcopy(source)
    old_page_id = page.id
    new_page_id = _id("page")
    page.id = new_page_id
    page.name = name or f"{source.name} - cópia"

    node_map = {old_id: _id("node") for old_id in page.nodes}
    slot_map = {old_id: _id("slot") for old_id in page.slots}
    id_map = {old_page_id: new_page_id, **node_map, **slot_map}

    new_nodes = {}
    for old_id, node in list(page.nodes.items()):
        node.id = node_map[old_id]
        node.parent_id = node_map.get(node.parent_id, node.parent_id)
        node.children = [node_map.get(child_id, child_id) for child_id in node.children]
        node.metadata = _remap_exact_references(node.metadata, id_map)
        node.style = _remap_exact_references(node.style, id_map)

        for key in _SEMANTIC_NODE_METADATA_KEYS:
            node.metadata.pop(key, None)
        for key in _SEMANTIC_NODE_STYLE_KEYS:
            node.style.pop(key, None)

        new_nodes[node.id] = node

    page.nodes = new_nodes
    page.roots = [node_map.get(node_id, node_id) for node_id in page.roots]

    new_slots = {}
    for old_id, slot in list(page.slots.items()):
        slot.id = slot_map[old_id]
        slot.page_id = new_page_id
        slot.node_by_role = {
            role: node_map.get(node_id, node_id)
            for role, node_id in slot.node_by_role.items()
        }
        slot.metadata = _remap_exact_references(slot.metadata, id_map)
        for key in _SEMANTIC_SLOT_METADATA_KEYS:
            slot.metadata.pop(key, None)
        new_slots[slot.id] = slot
    page.slots = new_slots

    page.metadata = _remap_exact_references(page.metadata, id_map)
    page.metadata.pop("semantic_blocks", None)
    page.metadata.pop("semantic_blocks_version", None)

    if rebuild_semantics:
        # Rebuild on an isolated one-page document so the source page and its
        # recovered slots remain untouched.
        isolated = GraphicsDocument(
            name="Duplicação de página",
            pages=[page],
            active_page_id=page.id,
        )
        build_semantic_blocks(isolated)

    return page


def duplicate_active_page(
    session: "GraphicsSession",
    *,
    name: str | None = None,
) -> str:
    """Duplicate the active page transactionally and activate the copy."""

    with session.transaction("Duplicar página"):
        page = clone_page_with_fresh_ids(session.page, name=name)
        session.document.pages.append(page)
        session.document.active_page_id = page.id
    session.clear_selection()
    return page.id
