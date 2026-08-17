from __future__ import annotations

from typing import Any
import copy

from .model import GraphicsPage, _id


def clone_page_with_fresh_ids(source: GraphicsPage, *, name: str | None = None) -> GraphicsPage:
    """Clone one SR Scene page without reusing internal object identifiers.

    Page duplication must be a true independent editing surface. Reusing node,
    SmartSlot or semantic-block ids across pages makes bindings and automation
    ambiguous even when each page is stored in its own mapping. This helper
    remaps every internal identifier while preserving layout and product data.
    """

    page = copy.deepcopy(source)
    page.id = _id("page")
    page.name = name or f"{source.name} - cópia"

    node_map = {old_id: _id("node") for old_id in source.nodes}
    slot_map = {old_id: _id("slot") for old_id in source.slots}

    raw_blocks = source.metadata.get("semantic_blocks")
    source_blocks = raw_blocks if isinstance(raw_blocks, dict) else {}
    block_map = {str(old_id): _id("semantic") for old_id in source_blocks}
    id_map = {**node_map, **slot_map, **block_map, source.id: page.id}

    new_nodes = {}
    for old_id, source_node in source.nodes.items():
        node = copy.deepcopy(source_node)
        node.id = node_map[old_id]
        node.parent_id = node_map.get(source_node.parent_id) if source_node.parent_id else None
        node.children = [node_map[child_id] for child_id in source_node.children if child_id in node_map]
        node.metadata = _remap_ids(node.metadata, id_map)
        node.style = _remap_ids(node.style, id_map)
        new_nodes[node.id] = node
    page.nodes = new_nodes
    page.roots = [node_map[node_id] for node_id in source.roots if node_id in node_map]

    new_slots = {}
    for old_slot_id, source_slot in source.slots.items():
        slot = copy.deepcopy(source_slot)
        slot.id = slot_map[old_slot_id]
        slot.page_id = page.id
        slot.node_by_role = {
            str(role): node_map[node_id]
            for role, node_id in source_slot.node_by_role.items()
            if node_id in node_map
        }
        slot.metadata = _remap_ids(slot.metadata, id_map)
        new_slots[slot.id] = slot
    page.slots = new_slots

    page.metadata = _remap_ids(copy.deepcopy(source.metadata), id_map)
    remapped_blocks = page.metadata.get("semantic_blocks")
    if isinstance(remapped_blocks, dict):
        normalized_blocks: dict[str, Any] = {}
        for old_block_id, source_block in source_blocks.items():
            new_block_id = block_map[str(old_block_id)]
            block = _remap_ids(copy.deepcopy(source_block), id_map)
            if isinstance(block, dict):
                block["id"] = new_block_id
            normalized_blocks[new_block_id] = block
        page.metadata["semantic_blocks"] = normalized_blocks

    return page


def _remap_ids(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_remap_ids(item, mapping) for item in value]
    if isinstance(value, tuple):
        return tuple(_remap_ids(item, mapping) for item in value)
    if isinstance(value, set):
        return {_remap_ids(item, mapping) for item in value}
    if isinstance(value, dict):
        return {
            mapping.get(str(key), str(key)): _remap_ids(item, mapping)
            for key, item in value.items()
        }
    return copy.deepcopy(value)
