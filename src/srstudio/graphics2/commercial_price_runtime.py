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

from . import semantic_named_slot_runtime as named_runtime
from .model import GraphicsDocument, NodeKind


def apply_commercial_price_blocks(semantic_module: Any, document: GraphicsDocument, report: Any) -> int:
    created = 0
    for page in document.pages:
        raw_blocks = page.metadata.get("semantic_blocks")
        if not isinstance(raw_blocks, dict):
            continue

        for slot in page.slots.values():
            # Saved v2 named slots keep their stable ID/product state and are
            # enriched in place with the v3 commercial bindings when those
            # explicitly named nodes exist in the scene.
            _upgrade_saved_named_slot(page, slot)
            _attach_named_fields_to_product_card(
                semantic_module,
                page,
                raw_blocks,
                slot,
            )

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


def _upgrade_saved_named_slot(page: Any, slot: Any) -> bool:
    if not bool(slot.metadata.get("explicit_named_semantics")):
        return False

    name_id = str(slot.node_by_role.get("name") or "")
    product = page.node(name_id)
    if product is None:
        return False

    changed = False
    extras = _normalized_extra_map(slot.metadata.get("extra_bindings"))
    text_nodes = [node for node in page.nodes.values() if node.kind is NodeKind.TEXT]
    primary = page.node(str(slot.node_by_role.get("price_complete") or "")) or product

    if not _valid_node_ids(page, extras.get("wholesale_price")):
        candidates = [node for node in text_nodes if named_runtime._is_wholesale_price_marker(node)]
        wholesale = named_runtime._nearest_node(
            page,
            primary,
            candidates,
            set(),
            max_dx=0.52,
            max_dy=0.58,
        )
        if wholesale is not None:
            extras["wholesale_price"] = [wholesale.id]
            slot.metadata["wholesale_price_node_id"] = wholesale.id
            changed = True

            currencies = [
                node
                for node in text_nodes
                if named_runtime._CURRENCY_RE.fullmatch(named_runtime._clean_text(node.text))
            ]
            excluded = _bound_currency_ids(slot)
            currency = named_runtime._nearest_price_companion(
                page,
                wholesale,
                currencies,
                exclude=excluded,
            )
            if currency is not None:
                extras["wholesale_price_currency"] = [currency.id]
                slot.metadata["wholesale_currency_node_id"] = currency.id

    if not str(slot.node_by_role.get("quantity") or ""):
        quantity_candidates = [node for node in text_nodes if named_runtime._is_quantity_marker(node)]
        quantity = named_runtime._nearest_or_unique(
            page,
            page.node(str(slot.metadata.get("wholesale_price_node_id") or "")) or primary,
            quantity_candidates,
            set(),
            max_dx=0.62,
            max_dy=0.65,
        )
        if quantity is not None:
            slot.node_by_role["quantity"] = quantity.id
            slot.metadata["quantity_node_id"] = quantity.id
            changed = True

    if extras:
        slot.metadata["extra_bindings"] = extras
    if changed or int(slot.metadata.get("explicit_named_semantics_version") or 0) < 3:
        slot.metadata["explicit_named_semantics_version"] = 3
        changed = True
    return changed


def _bound_currency_ids(slot: Any) -> set[str]:
    excluded: set[str] = set()
    for role in ("currency", "price_currency"):
        node_id = str(slot.node_by_role.get(role) or "")
        if node_id:
            excluded.add(node_id)
    extras = _normalized_extra_map(slot.metadata.get("extra_bindings"))
    for role in ("app_price_currency", "wholesale_price_currency"):
        excluded.update(extras.get(role, []))
    return excluded


def _attach_named_fields_to_product_card(
    semantic_module: Any,
    page: Any,
    raw_blocks: dict[str, Any],
    slot: Any,
) -> int:
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    card = raw_blocks.get(card_id)
    if not isinstance(card, dict):
        return 0

    members = [str(node_id) for node_id in card.get("members") or [] if str(node_id) in page.nodes]
    before = len(members)
    quantity_id = str(slot.node_by_role.get("quantity") or "")
    if quantity_id in page.nodes and quantity_id not in members:
        members.append(quantity_id)
        page.nodes[quantity_id].metadata["semantic_product_card_id"] = card_id

    if len(members) == before:
        return 0
    _refresh_card_geometry(semantic_module, page, card, members)
    return len(members) - before


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

    _refresh_card_geometry(semantic_module, page, card, members)


def _refresh_card_geometry(semantic_module: Any, page: Any, card: dict[str, Any], members: list[str]) -> None:
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


def _normalized_extra_map(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    output: dict[str, list[str]] = {}
    for role, values in raw.items():
        if isinstance(values, str):
            node_ids = [values]
        elif isinstance(values, (list, tuple, set)):
            node_ids = [str(node_id) for node_id in values if str(node_id)]
        else:
            node_ids = []
        if node_ids:
            output[str(role)] = list(dict.fromkeys(node_ids))
    return output


def _append_unique(metadata: dict[str, Any], key: str, value: str) -> None:
    current = metadata.get(key)
    values = list(current) if isinstance(current, (list, tuple)) else []
    if value not in values:
        values.append(value)
    metadata[key] = values
