from __future__ import annotations

"""Compatibilidade entre o semantic_blocks v8 e os runtimes comerciais CHAT 4.

A linha oficial ganhou recuperação nativa de preço completo depois do checkpoint
usado pelo CHAT 4. Esta camada mantém ambos os contratos: migra slots nomeados
v2 em memória antes da heurística espacial e garante o alias canônico
``retail_price`` nos slots espaciais promovidos a partir de um PriceBlock
``complete``.
"""

from typing import Any, Callable

from .model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot


def install_product_semantic_compat_guard(semantic_module: Any, named_module: Any) -> None:
    if bool(getattr(semantic_module, "_sr_product_semantic_compat_installed", False)):
        return

    original: Callable[..., Any] = semantic_module.build_semantic_blocks

    def guarded_build(document: GraphicsDocument, *args: Any, **kwargs: Any):
        _upgrade_saved_named_slots(document, named_module)
        report = original(document, *args, **kwargs)
        _ensure_recovered_complete_alias(document)
        return report

    guarded_build.__name__ = original.__name__
    guarded_build.__doc__ = original.__doc__
    guarded_build.__module__ = original.__module__
    semantic_module._sr_product_semantic_compat_original = original
    semantic_module.build_semantic_blocks = guarded_build
    semantic_module._sr_product_semantic_compat_installed = True


def _upgrade_saved_named_slots(document: GraphicsDocument, named: Any) -> None:
    upgraded = 0
    for page in document.pages:
        text_nodes = [node for node in page.nodes.values() if node.kind is NodeKind.TEXT and node.visible]
        images = [node for node in page.nodes.values() if node.kind is NodeKind.IMAGE and node.visible]
        for slot in list(page.slots.values()):
            metadata = slot.metadata if isinstance(slot.metadata, dict) else {}
            if not bool(metadata.get("explicit_named_semantics")):
                continue
            if int(metadata.get("explicit_named_semantics_version", 0) or 0) >= 3:
                continue
            product = page.nodes.get(str(slot.node_by_role.get("name") or ""))
            if product is None:
                continue

            primary = page.nodes.get(str(slot.node_by_role.get("price_complete") or slot.node_by_role.get("retail_price") or ""))
            if primary is None:
                candidates = [node for node in text_nodes if named._is_primary_price_marker(node)]
                primary = named._nearest_node(page, product, candidates, set(), max_dx=0.48, max_dy=0.48)

            secondary_prices = [node for node in text_nodes if named._is_secondary_price_marker(node)]
            wholesale_prices = [node for node in text_nodes if named._is_wholesale_price_marker(node)]
            anchor = primary or product
            secondary = named._nearest_node(page, anchor, secondary_prices, set(), max_dx=0.52, max_dy=0.58)
            wholesale = named._nearest_node(page, anchor, wholesale_prices, set(), max_dx=0.52, max_dy=0.58)

            primary_units = [node for node in text_nodes if named._is_primary_unit_marker(node)]
            secondary_units = [node for node in text_nodes if named._is_secondary_unit_marker(node)]
            currencies = [node for node in text_nodes if named._CURRENCY_RE.fullmatch(named._clean_text(node.text))]
            quantity_nodes = [node for node in text_nodes if named._is_quantity_marker(node)]
            limit_nodes = [node for node in text_nodes if named._is_limit_marker(node)]

            primary_unit = page.nodes.get(str(slot.node_by_role.get("unit") or ""))
            if primary_unit is None and primary is not None:
                primary_unit = named._nearest_price_companion(page, primary, primary_units)
            primary_currency = page.nodes.get(str(slot.node_by_role.get("price_currency") or ""))
            if primary_currency is None and primary is not None:
                primary_currency = named._nearest_price_companion(page, primary, currencies)

            excluded_currency = {primary_currency.id} if primary_currency is not None else set()
            secondary_currency = (
                named._nearest_price_companion(page, secondary, currencies, exclude=excluded_currency)
                if secondary is not None
                else None
            )
            if secondary_currency is not None:
                excluded_currency.add(secondary_currency.id)
            wholesale_currency = (
                named._nearest_price_companion(page, wholesale, currencies, exclude=excluded_currency)
                if wholesale is not None
                else None
            )
            secondary_unit = (
                named._nearest_price_companion(page, secondary, secondary_units)
                if secondary is not None
                else None
            )
            quantity = named._nearest_or_unique(
                page,
                wholesale or primary or product,
                quantity_nodes,
                set(),
                max_dx=0.62,
                max_dy=0.65,
            )
            limit = named._nearest_or_unique(
                page,
                product,
                limit_nodes,
                set(),
                max_dx=0.60,
                max_dy=0.65,
            )
            image = named._explicit_product_image(page, product, images)

            # Preserve identidade/estado do slot salvo; somente amplia bindings.
            slot.node_by_role["name"] = product.id
            if primary is not None:
                slot.node_by_role["price_complete"] = primary.id
            if primary_currency is not None:
                slot.node_by_role["price_currency"] = primary_currency.id
            if primary_unit is not None:
                slot.node_by_role["unit"] = primary_unit.id
            if quantity is not None:
                slot.node_by_role["quantity"] = quantity.id
            if limit is not None:
                slot.node_by_role["limit"] = limit.id
            if image is not None:
                slot.node_by_role["image"] = image.id

            extras = metadata.get("extra_bindings")
            extra_bindings = dict(extras) if isinstance(extras, dict) else {}
            if secondary is not None:
                extra_bindings["app_price_complete"] = [secondary.id]
                if secondary_currency is not None:
                    extra_bindings["app_price_currency"] = [secondary_currency.id]
                if secondary_unit is not None:
                    extra_bindings["app_unit"] = [secondary_unit.id]
            if wholesale is not None:
                extra_bindings["wholesale_price"] = [wholesale.id]
                if wholesale_currency is not None:
                    extra_bindings["wholesale_price_currency"] = [wholesale_currency.id]

            metadata["explicit_named_semantics_version"] = 3
            metadata["primary_price_node_id"] = primary.id if primary is not None else ""
            metadata["secondary_price_node_id"] = secondary.id if secondary is not None else ""
            metadata["wholesale_price_node_id"] = wholesale.id if wholesale is not None else ""
            metadata["wholesale_currency_node_id"] = wholesale_currency.id if wholesale_currency is not None else ""
            metadata["quantity_node_id"] = quantity.id if quantity is not None else ""
            metadata["limit_node_id"] = limit.id if limit is not None else ""
            metadata["extra_bindings"] = extra_bindings
            slot.metadata = metadata
            upgraded += 1

    if upgraded:
        document.metadata["explicit_named_slots_migration"] = {
            "version": 3,
            "upgraded": upgraded,
            "source": "integration-semantic-v8-compat",
        }


def _ensure_recovered_complete_alias(document: GraphicsDocument) -> None:
    retail_role = BindingRole.RETAIL_PRICE.value
    for page in document.pages:
        raw_blocks = page.metadata.get("semantic_blocks")
        blocks = raw_blocks if isinstance(raw_blocks, dict) else {}
        for slot in page.slots.values():
            if not bool(slot.metadata.get("semantic_recovered")):
                continue
            if slot.node_by_role.get(retail_role):
                continue
            complete_id = _complete_node_for_slot(slot, blocks)
            if complete_id and complete_id in page.nodes:
                slot.node_by_role[retail_role] = complete_id


def _complete_node_for_slot(slot: SmartSlot, blocks: dict[str, Any]) -> str:
    for raw in blocks.values():
        if not isinstance(raw, dict) or raw.get("kind") != "price_block":
            continue
        if str(raw.get("slot_id") or "") != slot.id:
            continue
        roles = raw.get("roles")
        if not isinstance(roles, dict):
            continue
        complete = roles.get("complete")
        if isinstance(complete, list) and complete:
            return str(complete[0])
    return ""
