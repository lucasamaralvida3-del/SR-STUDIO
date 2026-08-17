from __future__ import annotations

"""Atomic ProductCard field editing for the G2 flyer editor."""

from typing import Any, TYPE_CHECKING

from .asset_edit import _asset_for_source
from .model import BindingRole, NodeKind
from .price_edit import _parse_price, _unit_text

if TYPE_CHECKING:
    from .operations import GraphicsSession


_ROLE_ALIASES = {
    BindingRole.NAME.value: "name",
    "name": "name",
    BindingRole.IMAGE.value: "image",
    "image": "image",
    BindingRole.CURRENCY.value: "currency",
    "price_currency": "currency",
    BindingRole.PRICE_REAIS.value: "reais",
    "price_integer": "reais",
    BindingRole.PRICE_CENTS.value: "cents",
    "price_cents": "cents",
    "price_complete": "complete",
    BindingRole.UNIT.value: "unit",
    "unit": "unit",
    BindingRole.LIMIT.value: "limit",
    "limit": "limit",
    BindingRole.APP_PRICE.value: "app_complete",
    "app_price_complete": "app_complete",
    "app_price_currency": "app_currency",
    "app_price_integer": "app_reais",
    "app_price_cents": "app_cents",
    "app_unit": "app_unit",
}


def _bindings(slot) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for role, node_id in slot.node_by_role.items():
        canonical = _ROLE_ALIASES.get(str(role))
        if canonical and node_id:
            result.setdefault(canonical, []).append(str(node_id))
    for role, node_ids in dict(slot.metadata.get("extra_bindings") or {}).items():
        canonical = _ROLE_ALIASES.get(str(role))
        if not canonical or not isinstance(node_ids, (list, tuple)):
            continue
        for node_id in node_ids:
            if node_id:
                result.setdefault(canonical, []).append(str(node_id))
    return result


def _set_text(session: "GraphicsSession", ids: list[str], value: str, *, optional: bool = False) -> None:
    for node_id in ids:
        node = session.page.node(node_id)
        if node is None or node.kind is not NodeKind.TEXT:
            continue
        node.text = value
        if optional:
            node.visible = bool(value)
        elif value:
            node.visible = True


def edit_product_card(
    session: "GraphicsSession",
    slot_id: str,
    *,
    name: str | None = None,
    price: object | None = None,
    unit: object | None = None,
    image_source: str | None = None,
    limit: str | None = None,
    app_price: object | None = None,
) -> bool:
    """Edit card data as a single undoable operation, preserving geometry/style."""

    slot = session.page.slots.get(str(slot_id))
    if slot is None or slot.locked:
        return False
    bindings = _bindings(slot)
    touched_ids = {node_id for ids in bindings.values() for node_id in ids}
    if any(session.effective_locked(node_id) for node_id in touched_ids if session.page.node(node_id) is not None):
        return False

    requested = any(value is not None for value in (name, price, unit, image_source, limit, app_price))
    if not requested:
        return False

    primary_parts = _parse_price(price) if price is not None else None
    app_parts = _parse_price(app_price) if app_price is not None else None

    with session.transaction("Editar ProductCard"):
        snapshot: dict[str, Any] = dict(slot.metadata.get("product_snapshot") or {})

        if name is not None:
            value = str(name).strip()
            _set_text(session, bindings.get("name", []), value)
            snapshot["display_name"] = value
            snapshot["name"] = value

        if primary_parts is not None:
            whole, cents, complete = primary_parts
            _set_text(session, bindings.get("currency", []), "R$")
            _set_text(session, bindings.get("reais", []), whole)
            _set_text(session, bindings.get("cents", []), cents)
            _set_text(session, bindings.get("complete", []), f"R$ {complete}")
            snapshot["price"] = complete

        if unit is not None:
            raw_unit = str(unit or "").upper().strip().lstrip("/")
            for node_id in bindings.get("unit", []):
                node = session.page.node(node_id)
                if node is not None and node.kind is NodeKind.TEXT:
                    node.text = _unit_text(raw_unit, node.text)
                    node.visible = bool(node.text)
            snapshot["unit"] = raw_unit

        if image_source is not None:
            source = str(image_source or "").strip()
            if source:
                asset = _asset_for_source(session, source)
                for node_id in bindings.get("image", []):
                    node = session.page.node(node_id)
                    if node is None or node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
                        continue
                    node.asset_id = asset.id
                    node.metadata["bound_image_source"] = asset.source
                    node.metadata["manual_image_replacement"] = True
                    node.visible = True
                snapshot["image_path"] = asset.source

        if limit is not None:
            raw_limit = str(limit or "").strip()
            value = f"LIMITE DE {raw_limit} POR CPF" if raw_limit else ""
            _set_text(session, bindings.get("limit", []), value, optional=True)
            snapshot["limit"] = raw_limit
            snapshot["cpf_limit"] = raw_limit

        if app_parts is not None:
            whole, cents, complete = app_parts
            _set_text(session, bindings.get("app_currency", []), "R$", optional=True)
            _set_text(session, bindings.get("app_reais", []), whole, optional=True)
            _set_text(session, bindings.get("app_cents", []), cents, optional=True)
            _set_text(session, bindings.get("app_complete", []), f"R$ {complete}", optional=True)
            if unit is not None:
                raw_unit = str(unit or "").upper().strip().lstrip("/")
                for node_id in bindings.get("app_unit", []):
                    node = session.page.node(node_id)
                    if node is not None and node.kind is NodeKind.TEXT:
                        node.text = _unit_text(raw_unit, node.text)
                        node.visible = bool(node.text)
            snapshot["app_price"] = complete

        slot.metadata["product_snapshot"] = snapshot

    return True
