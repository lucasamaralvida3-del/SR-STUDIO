from __future__ import annotations

"""Product binding adapter for supervised Quinta 3 ItemSlot families.

The generic ItemSlot path is reused.  This adapter preserves source-specific
surface semantics that older templates intentionally format differently:
literal UNIT text, a second split promotional PriceBlock, independent labels
and multi-node IMAGE copies sharing the same product asset.
"""

from copy import deepcopy
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
        # Older ItemSlots use '/KG'.  Quinta 3 deliberately uses the exact PPTX
        # spelling KG/UN/CADA/QUILO, so only this supervised adapter removes '/'.
        unit_node = page.node(str(slot.node_by_role.get(BindingRole.UNIT.value) or ""))
        unit = str(product.get("unit") or "UN").strip().upper().lstrip("/")
        if unit_node is not None and unit_node.kind is NodeKind.TEXT:
            unit_node.text = unit

        extras = slot.metadata.get("extra_bindings")
        extras = extras if isinstance(extras, dict) else {}
        _bind_image_copies(page, slot, extras, product)

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
            snapshot["quinta3_variant"] = str(slot.metadata.get("quinta3_variant") or "")
            snapshot["quinta3_parameters"] = deepcopy(slot.metadata.get("quinta3_parameters") or {})
            snapshot["image_copies"] = int(slot.metadata.get("image_copies") or 1)
        refresh_item_slot_metadata(page, slot)
    return True


def _bind_image_copies(page, slot, extras: dict[str, Any], product: dict[str, Any]) -> None:
    source = page.node(str(slot.node_by_role.get(BindingRole.IMAGE.value) or ""))
    if source is None or source.kind is not NodeKind.IMAGE:
        return

    # Keep the generic binder as the primary path, but make the supervised
    # multi-node contract explicit here.  This also covers callers that provide
    # only ``image_asset_id`` and no filesystem image source.
    asset_id = str(product.get("image_asset_id") or source.asset_id or "")
    image_source = str(product.get("image_path") or product.get("image") or source.metadata.get("bound_image_source") or "")
    if asset_id:
        source.asset_id = asset_id
    if image_source:
        source.metadata["bound_image_source"] = image_source
    source.metadata["placeholder"] = False

    raw_ids = extras.get(BindingRole.IMAGE.value)
    ids = raw_ids if isinstance(raw_ids, (list, tuple)) else []
    for raw_id in ids:
        node = page.node(str(raw_id or ""))
        if node is None or node.kind is not NodeKind.IMAGE:
            continue
        node.asset_id = asset_id
        node.style = deepcopy(source.style)
        node.metadata["placeholder"] = False
        if image_source:
            node.metadata["bound_image_source"] = image_source
        if source.metadata.get("image_sha256"):
            node.metadata["image_sha256"] = source.metadata["image_sha256"]


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
