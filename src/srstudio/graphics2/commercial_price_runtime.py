from __future__ import annotations

"""Commercial PriceBlock extension for G2 SmartSlots.

The historical semantic builder has dedicated primary and Club/App PriceBlocks.
Wholesale/Atacado is a distinct commercial value, not an app price, so this
runtime adds a third PriceBlock only when a SmartSlot explicitly exposes
``wholesale_price`` bindings.

This is post-processing over SR Scene nodes. It does not parse PPTX/Canva files
and therefore stays on the Product System side of the parallel work boundary.
"""

from typing import Any

from .model import GraphicsDocument


def apply_commercial_price_blocks(semantic_module: Any, document: GraphicsDocument, report: Any) -> int:
    created = 0
    for page in document.pages:
        raw_blocks = page.metadata.get("semantic_blocks")
        if not isinstance(raw_blocks, dict):
            continue

        for slot in page.slots.values():
            extras = slot.metadata.get("extra_bindings")
            if not isinstance(extras, dict):
                continue

            price_ids = _valid_node_ids(page, extras.get("wholesale_price"))
            if not price_ids:
                continue

            roles: dict[str, list[str]] = {"complete": price_ids}
            currency_ids = _valid_node_ids(page, extras.get("wholesale_price_currency"))
            unit_ids = _valid_node_ids(page, extras.get("wholesale_unit"))
            if currency_ids:
                roles["currency"] = currency_ids
            if unit_ids:
                roles["unit"] = unit_ids

            block_id = f"priceblock:{slot.id}:wholesale-price"
            block = semantic_module._make_price_block(
                page,
                block_id,
                slot.id,
                roles,
                source=str(slot.metadata.get("source") or "smart-slot"),
            )
            block.metadata["commercial_role"] = "wholesale"
            block.metadata["price_field"] = "wholesale_price"
            raw_blocks[block.id] = block.to_dict()

            report.price_blocks += 1
            report.protected_price_nodes += len(block.members)
            if not bool(block.metadata.get("complete")):
                report.incomplete_price_blocks += 1

            _attach_to_product_card(semantic_module, page, raw_blocks, slot, block)
            _append_unique(slot.metadata, "semantic_price_block_ids", block.id)
            created += 1

    if created:
        document.metadata["commercial_price_blocks"] = {
            "version": 1,
            "wholesale_price_blocks": created,
        }
    else:
        document.metadata.pop("commercial_price_blocks", None)

    # The historical builder stores report.to_dict() before this post-pass.
    # Refresh it so diagnostics/usability see the real final semantic counts.
    document.metadata["semantic_blocks"] = report.to_dict()
    return created


def _attach_to_product_card(
    semantic_module: Any,
    page: Any,
    raw_blocks: dict[str, Any],
    slot: Any,
    block: Any,
) -> None:
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    card = raw_blocks.get(card_id)
    if not isinstance(card, dict):
        return

    metadata = card.setdefault("metadata", {})
    price_blocks = metadata.setdefault("price_blocks", [])
    if block.id not in price_blocks:
        price_blocks.append(block.id)

    members = [str(node_id) for node_id in card.get("members") or [] if str(node_id) in page.nodes]
    for node_id in block.members:
        if node_id not in members:
            members.append(node_id)
        page.nodes[node_id].metadata["semantic_product_card_id"] = card_id

    card["members"] = members
    bounds = semantic_module._bounds_dict(page, members)
    card["bounds"] = bounds
    card["template_geometry"] = {
        node_id: semantic_module._geometry(page.nodes[node_id], bounds)
        for node_id in members
    }


def _valid_node_ids(page: Any, raw: Any) -> list[str]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = []
    return list(dict.fromkeys(str(node_id) for node_id in values if str(node_id) in page.nodes))


def _append_unique(metadata: dict[str, Any], key: str, value: str) -> None:
    current = metadata.get(key)
    values = list(current) if isinstance(current, (list, tuple)) else []
    if value not in values:
        values.append(value)
    metadata[key] = values
