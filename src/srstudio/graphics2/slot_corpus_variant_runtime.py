from __future__ import annotations

"""Runtime materialization for supervised Quinta 3 ItemSlot variants.

This stays on top of the existing manual ItemSlot architecture: the base slot is
created by ``create_item_slot`` and only source-proven parametric roles are
added.  Secondary price is represented as a second split PriceBlock through the
existing ``app_price_*`` extra-binding contract.  PROMOTION and CLUB remain
independent semantic roles and are never appended to NAME.
"""

from copy import deepcopy
from typing import Any

from .item_slots import create_item_slot
from .model import BindingRole, GraphicsNode, NodeKind, Rect, Transform
from .operations import GraphicsSession
from .slot_corpus_families import QUINTA3_FAMILY_PRESETS, install_quinta3_family_presets

# Internal component geometry is relative to the secondary-price group.  These
# values are medians from the exact PPTX family members, not generic retail
# heuristics.
_SECONDARY_COMPONENTS: dict[tuple[str, str], dict[str, list[float]]] = {
    ("quinta3-wood-plaque", "club-promo"): {
        "currency": [0.0000, 0.3095, 0.1976, 0.4256],
        "integer": [0.3498, 0.0000, 0.2292, 1.0000],
        "decimal": [0.7462, 0.0749, 0.2538, 0.5337],
        "unit": [0.7840, 0.5874, 0.1776, 0.3220],
    },
    ("quinta3-compact-promo", "blue"): {
        "currency": [0.0000, 0.4169, 0.1940, 0.3380],
        "integer": [0.3106, 0.0000, 0.3113, 1.0000],
        "decimal": [0.7141, 0.2556, 0.2859, 0.3823],
        "unit": [0.8263, 0.5523, 0.1742, 0.3634],
    },
    ("quinta3-compact-promo", "beige"): {
        "currency": [0.0000, 0.3448, 0.1940, 0.3989],
        "integer": [0.3063, 0.0000, 0.2538, 1.0000],
        "decimal": [0.7141, 0.1761, 0.2859, 0.4452],
        "unit": [0.7604, 0.5781, 0.1964, 0.4021],
    },
    ("quinta3-club-side", "club-promo"): {
        "currency": [0.0000, 0.2825, 0.2119, 0.4008],
        "integer": [0.3028, 0.0000, 0.3333, 1.0000],
        "decimal": [0.7086, 0.1637, 0.2914, 0.4462],
        "unit": [0.7580, 0.6112, 0.1904, 0.2840],
    },
}


def create_quinta3_item_slot(
    session: GraphicsSession,
    family_id: str,
    *,
    variant: str = "default",
    parameters: dict[str, Any] | None = None,
    x: float | None = None,
    y: float | None = None,
):
    """Create one reusable slot family and materialize a source-proven variant."""

    family_id = str(family_id or "").strip()
    if family_id not in QUINTA3_FAMILY_PRESETS:
        raise KeyError(f"Família Quinta 3 inexistente: {family_id}")
    install_quinta3_family_presets(session.document)
    slot = create_item_slot(session, family_id, x=x, y=y)
    apply_quinta3_variant(session, slot.id, variant=variant, parameters=parameters)
    return slot


def apply_quinta3_variant(
    session: GraphicsSession,
    slot_id: str,
    *,
    variant: str = "default",
    parameters: dict[str, Any] | None = None,
) -> bool:
    slot = session.page.slots.get(str(slot_id))
    if slot is None or not slot.metadata.get("manual_item_slot"):
        return False
    family_id = str(slot.metadata.get("preset_id") or "")
    family = QUINTA3_FAMILY_PRESETS.get(family_id)
    if family is None:
        return False

    variants = dict(family.get("metadata", {}).get("variants") or {})
    variant_key = str(variant or "default").strip()
    if variant_key not in variants:
        if len(variants) == 1:
            variant_key = next(iter(variants))
        elif "default" not in variants:
            raise KeyError(f"Variante inexistente para {family_id}: {variant}")
        else:
            variant_key = "default"
    resolved = deepcopy(variants.get(variant_key) or {})
    resolved.update(deepcopy(parameters or {}))

    page = session.page
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return False
    root_rect = root.rect.normalized()

    with session.transaction("Aplicar Variante de Slot Quinta 3"):
        _apply_role_overrides(page, slot, root_rect, dict(resolved.get("role_overrides") or {}))
        _remove_variant_nodes(page, slot)
        extras = slot.metadata.setdefault("extra_bindings", {})
        if not isinstance(extras, dict):
            extras = {}
            slot.metadata["extra_bindings"] = extras
        for key in list(extras):
            if key.startswith("app_price_") or key in {"promotion", "club_label"}:
                extras.pop(key, None)

        optional = dict(resolved.get("optional_roles") or {})
        created: list[str] = []
        if bool(resolved.get("secondaryPriceVisible")) and optional.get("secondaryPrice"):
            created.extend(_add_secondary_price(page, root.id, root_rect, family_id, variant_key, optional["secondaryPrice"], extras))
        if bool(resolved.get("promotionVisible")) and optional.get("promotion"):
            node = _add_label(page, root.id, root_rect, optional["promotion"], "PROMOTION ROLE", "PROMOÇÃO")
            extras["promotion"] = [node.id]
            created.append(node.id)
        if bool(resolved.get("clubVisible")) and optional.get("club"):
            node = _add_label(page, root.id, root_rect, optional["club"], "CLUB ROLE", "NO SR CLUBE SMART")
            extras["club_label"] = [node.id]
            created.append(node.id)

        slot.metadata["quinta3_family"] = family_id
        slot.metadata["quinta3_variant"] = variant_key
        slot.metadata["quinta3_parameters"] = deepcopy(resolved)
        slot.metadata["quinta3_variant_nodes"] = created
        slot.metadata["image_copies"] = max(1, int(resolved.get("imageCopies") or 1))
        slot.metadata["source_supervised_geometry"] = True
        slot.metadata["promotion_visible"] = bool(resolved.get("promotionVisible"))
        slot.metadata["club_visible"] = bool(resolved.get("clubVisible"))
        slot.metadata["secondary_price_visible"] = bool(resolved.get("secondaryPriceVisible"))
    return True


def _apply_role_overrides(page, slot, root: Rect, overrides: dict[str, Any]) -> None:
    if not overrides:
        return
    areas = dict(slot.metadata.get("role_area_nodes") or {})
    for role in ("image", "name", "unit"):
        raw = overrides.get(role)
        node = page.node(str(areas.get(role) or ""))
        if node is None or not isinstance(raw, (list, tuple)) or len(raw) != 4:
            continue
        target = _absolute(root, raw)
        _set_rect(node, target)

    raw_price = overrides.get("price")
    price_group = page.node(str(areas.get("price") or ""))
    if price_group is not None and isinstance(raw_price, (list, tuple)) and len(raw_price) == 4:
        old = price_group.rect.normalized()
        target = _absolute(root, raw_price)
        descendants = [page.node(node_id) for node_id in page.descendants(price_group.id)]
        for node in descendants:
            if node is None:
                continue
            _set_rect(node, _map_rect(node.rect.normalized(), old, target))
        _set_rect(price_group, target)


def _remove_variant_nodes(page, slot) -> None:
    for node_id in list(slot.metadata.get("quinta3_variant_nodes") or []):
        if node_id not in page.nodes:
            continue
        descendants = list(page.descendants(node_id))
        for child_id in reversed(descendants):
            page.remove_node(child_id)
        if node_id in page.nodes:
            page.remove_node(node_id)
    slot.metadata["quinta3_variant_nodes"] = []


def _add_secondary_price(
    page,
    root_id: str,
    root: Rect,
    family_id: str,
    variant: str,
    bounds: Any,
    extras: dict[str, Any],
) -> list[str]:
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        return []
    price_rect = _absolute(root, bounds)
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="SECONDARY PRICE AREA",
        transform=Transform(x=price_rect.x, y=price_rect.y, width=price_rect.width, height=price_rect.height),
        metadata={"manual_item_slot_child": True, "item_slot_role_area": "secondary_price", "quinta3_variant_node": True},
    )
    page.add_node(group, parent_id=root_id)

    layout = _SECONDARY_COMPONENTS.get((family_id, variant)) or {
        "currency": [0.00, 0.28, 0.20, 0.42],
        "integer": [0.25, 0.00, 0.40, 1.00],
        "decimal": [0.68, 0.12, 0.32, 0.45],
        "unit": [0.78, 0.60, 0.20, 0.30],
    }
    specs = (
        ("app_price_currency", "R$", "currency", 10.0),
        ("app_price_integer", "00", "integer", 27.0),
        ("app_price_cents", ",00", "decimal", 12.0),
        ("app_unit", "UN", "unit", 9.0),
    )
    created = [group.id]
    for binding, text, key, size in specs:
        rect = _absolute(price_rect, layout[key])
        node = GraphicsNode(
            kind=NodeKind.TEXT,
            name=binding.upper(),
            text=text,
            transform=Transform(x=rect.x, y=rect.y, width=rect.width, height=rect.height),
            style={
                "font_family": "Anton",
                "font_size": size,
                "font_size_unit": "pt",
                "font_weight": 700,
                "fill": "#FFFFFF",
                "align": "center",
                "v_align": "center",
                "fit_inside_box": True,
                "nowrap": True,
            },
            metadata={"manual_item_slot_child": True, "quinta3_variant_node": True, "item_slot_price_component": binding},
        )
        page.add_node(node, parent_id=group.id)
        extras[binding] = [node.id]
        created.append(node.id)
    return created


def _add_label(page, root_id: str, root: Rect, bounds: Any, name: str, text: str) -> GraphicsNode:
    rect = _absolute(root, bounds)
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        transform=Transform(x=rect.x, y=rect.y, width=rect.width, height=rect.height),
        style={
            "font_family": "Anton",
            "font_size": 9.0,
            "font_size_unit": "pt",
            "font_weight": 700,
            "fill": "#FFFFFF",
            "align": "center",
            "v_align": "center",
            "fit_inside_box": True,
        },
        metadata={"manual_item_slot_child": True, "quinta3_variant_node": True},
    )
    page.add_node(node, parent_id=root_id)
    return node


def _absolute(parent: Rect, relative: Any) -> Rect:
    x, y, width, height = (float(value) for value in relative)
    return Rect(
        parent.x + x * parent.width,
        parent.y + y * parent.height,
        max(1.0, width * parent.width),
        max(1.0, height * parent.height),
    )


def _map_rect(child: Rect, old: Rect, new: Rect) -> Rect:
    return Rect(
        new.x + ((child.x - old.x) / max(old.width, 1e-9)) * new.width,
        new.y + ((child.y - old.y) / max(old.height, 1e-9)) * new.height,
        (child.width / max(old.width, 1e-9)) * new.width,
        (child.height / max(old.height, 1e-9)) * new.height,
    )


def _set_rect(node: GraphicsNode, rect: Rect) -> None:
    node.transform.x = rect.x
    node.transform.y = rect.y
    node.transform.width = max(1.0, rect.width)
    node.transform.height = max(1.0, rect.height)
