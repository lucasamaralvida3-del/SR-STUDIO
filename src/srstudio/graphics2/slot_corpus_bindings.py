from __future__ import annotations

"""Product binding adapter for supervised Quinta 3 ItemSlot families.

The adapter deliberately reuses the existing ItemSlot/Product binding path and
then applies only source-specific semantics that cannot be expressed by the
legacy generic role formatter: exact UNIT text (KG/UN/CADA/QUILO without an
invented slash) and an optional second split promotional price.
"""

from typing import Any

from .item_slots import bind_product_to_item_slot, refresh_item_slot_metadata
from .model import BindingRole, NodeKind
from .operations import GraphicsSession, _price_parts


def bind_product_to_quinta3_slot(session: GraphicsSession, slot_id: str, product: dict[str, Any]) -> bool:
    slot = session.page.slots.get(str(slot_id))
    if slot is None or not slot.metadata.get("quinta3_family"):
        return False
    if not bind_product_to_item_slot(session, slot.id, product):
        return False

    page = session.page
    with session.transaction("Aplicar Bindings Quinta 3"):
        # The exact corpus spells these as KG / UN / CADA / QUILO.  The generic
        # ItemSlot formatter prepends '/', which is valid for older templates but
        # would mutate this supervised source style.
        unit_node = page.node(str(slot.node_by_role.get(BindingRole.UNIT.value) or ""))
        unit = str(product.get("unit") or "UN").strip().upper().lstrip("/")
        if unit_node is not None and unit_node.kind is NodeKind.TEXT:
            unit_node.text = unit

        extras = slot.metadata.get("extra_bindings")
        extras = extras if isinstance(extras, dict) else {}
        secondary = _secondary_price_value(product)
        if secondary not in (None, "") and all(key in extras for key in ("app_price_integer", "app_price_cents")):
            whole, cents = _price_parts(secondary)
            _set_text(page, extras.get("app_price_currency"), "R$")
            _set_text(page, extras.get("app_price_integer"), whole)
            _set_text(page, extras.get("app_price_cents"), cents)
            secondary_unit = str(product.get("secondary_unit") or product.get("promotion_unit") or unit or "UN").strip().upper().lstrip("/")
            _set_text(page, extras.get("app_unit"), secondary_unit)

        promotion_label = str(product.get("promotion_label") or "PROMOÇÃO").strip()
        club_label = str(product.get("club_label") or "NO SR CLUBE SMART").strip()
        if slot.metadata.get("promotion_visible"):
            _set_text(page, extras.get("promotion"), promotion_label)
        if slot.metadata.get("club_visible"):
            _set_text(page, extras.get("club_label"), club_label)

        snapshot = slot.metadata.setdefault("product_snapshot", {})
        if isinstance(snapshot, dict):
            snapshot["quinta3_unit"] = unit
            snapshot["quinta3_secondary_price"] = "" if secondary in (None, "") else str(secondary)
            snapshot["quinta3_secondary_unit"] = str(product.get("secondary_unit") or product.get("promotion_unit") or "").strip().upper().lstrip("/")
        refresh_item_slot_metadata(page, slot)
    return True


def _secondary_price_value(product: dict[str, Any]) -> Any:
    for key in ("secondary_price", "promotion_price", "retail_price"):
        value = product.get(key)
        if value not in (None, ""):
            return value
    return None


def _set_text(page, raw_ids: Any, text: str) -> None:
    ids = raw_ids if isinstance(raw_ids, (list, tuple)) else [raw_ids]
    for raw_id in ids:
        node = page.node(str(raw_id or ""))
        if node is not None and node.kind is NodeKind.TEXT:
            node.text = str(text)
