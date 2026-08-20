from __future__ import annotations

"""Runtime materialization for the five supervised Quinta 3 ItemSlot families.

The five base preset IDs stay stable.  Source variations are parameters layered
on top of the existing manual ItemSlot architecture: exact role bounds,
secondary split PriceBlock, PROMOTION/CLUB labels and multi-node IMAGE copies.
"""

from copy import deepcopy
from typing import Any

from .item_slots import create_item_slot
from .model import BindingRole, GraphicsNode, NodeKind, Rect, Transform
from .operations import GraphicsSession
from .slot_corpus_calibration import profile_parameters
from .slot_corpus_families import QUINTA3_FAMILY_PRESETS, install_quinta3_family_presets
from .slot_corpus_full_card import MEAT_FAMILY_ID, apply_meat_strip_full_card

_SECONDARY_COMPONENTS: dict[tuple[str, str], dict[str, list[float]]] = {
    ("quinta3-wood-plaque", "club-promo"): {
        "currency": [0.0000, 0.3095, 0.1976, 0.4256], "integer": [0.3498, 0.0000, 0.2292, 1.0000],
        "decimal": [0.7462, 0.0749, 0.2538, 0.5337], "unit": [0.7840, 0.5874, 0.1776, 0.3220],
    },
    ("quinta3-compact-promo", "blue"): {
        "currency": [0.0000, 0.4169, 0.1940, 0.3380], "integer": [0.3106, 0.0000, 0.3113, 1.0000],
        "decimal": [0.7141, 0.2556, 0.2859, 0.3823], "unit": [0.8263, 0.5523, 0.1742, 0.3634],
    },
    ("quinta3-compact-promo", "beige"): {
        "currency": [0.0000, 0.3448, 0.1940, 0.3989], "integer": [0.3063, 0.0000, 0.2538, 1.0000],
        "decimal": [0.7141, 0.1761, 0.2859, 0.4452], "unit": [0.7604, 0.5781, 0.1964, 0.4021],
    },
    ("quinta3-club-side", "club-promo"): {
        "currency": [0.0000, 0.2825, 0.2119, 0.4008], "integer": [0.3028, 0.0000, 0.3333, 1.0000],
        "decimal": [0.7086, 0.1637, 0.2914, 0.4462], "unit": [0.7580, 0.6112, 0.1904, 0.2840],
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

    incoming = deepcopy(parameters or {})
    profile_id = str(incoming.get("supervisedProfile") or "").strip()
    if profile_id:
        calibrated = profile_parameters(profile_id)
        calibrated.update(incoming)
        incoming = calibrated

    variants = dict(family.get("metadata", {}).get("variants") or {})
    variant_key = str(variant or "default").strip()
    if variant_key not in variants:
        if len(variants) == 1:
            variant_key = next(iter(variants))
        elif "default" in variants:
            variant_key = "default"
        else:
            raise KeyError(f"Variante inexistente para {family_id}: {variant}")
    resolved = deepcopy(variants.get(variant_key) or {})
    resolved.update(incoming)

    page = session.page
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return False
    root_rect = root.rect.normalized()

    with session.transaction("Aplicar Variante de Slot Quinta 3"):
        _remove_variant_nodes(page, slot)
        extras = slot.metadata.setdefault("extra_bindings", {})
        if not isinstance(extras, dict):
            extras = {}
            slot.metadata["extra_bindings"] = extras
        for key in list(extras):
            if key.startswith("app_price_") or key in {"app_unit", "promotion", "club_label", BindingRole.IMAGE.value}:
                extras.pop(key, None)

        overrides = dict(resolved.get("role_overrides") or {})
        supervised = dict(resolved.get("roleBounds") or {})
        overrides.update({key: value for key, value in supervised.items() if key in {"image", "name", "price", "unit"}})
        _apply_role_overrides(page, slot, root_rect, overrides)

        created: list[str] = []
        image_copy_bounds = resolved.get("imageCopyBounds")
        image_count = max(1, int(resolved.get("imageCopies") or 1))
        created.extend(_materialize_image_copies(page, root.id, root_rect, slot, extras, image_count, image_copy_bounds))

        optional = dict(resolved.get("optional_roles") or {})
        for key in ("secondaryPrice", "promotion", "club"):
            if key in supervised:
                optional[key] = supervised[key]

        if bool(resolved.get("secondaryPriceVisible")) and optional.get("secondaryPrice"):
            layout = resolved.get("secondaryComponents")
            created.extend(_add_secondary_price(page, root.id, root_rect, family_id, variant_key, optional["secondaryPrice"], extras, layout))
        if bool(resolved.get("promotionVisible")) and optional.get("promotion"):
            node = _add_label(page, root.id, root_rect, optional["promotion"], "PROMOTION ROLE", "PROMOÇÃO")
            extras["promotion"] = [node.id]
            created.append(node.id)
        if bool(resolved.get("clubVisible")) and optional.get("club"):
            node = _add_label(page, root.id, root_rect, optional["club"], "CLUB ROLE", "NO SR CLUBE SMART")
            extras["club_label"] = [node.id]
            created.append(node.id)

        # New full-card fidelity definition.  Only Meat Strip is enabled in
        # this round: its real PPTX visual subtree replaces the synthetic
        # image/price backplates while the existing ItemSlot architecture and
        # bindings remain intact.  Do not apply this path to the other four
        # families until Meat Strip passes the visual/manual gate.
        if family_id == MEAT_FAMILY_ID:
            root_rect, full_card_nodes = apply_meat_strip_full_card(
                page,
                slot,
                profile_id=profile_id or "costela",
                requested_position=str(resolved.get("stripPosition") or ""),
            )
            created.extend(full_card_nodes)

        slot.metadata["quinta3_family"] = family_id
        slot.metadata["quinta3_variant"] = variant_key
        slot.metadata["quinta3_parameters"] = deepcopy(resolved)
        slot.metadata["quinta3_variant_nodes"] = created
        slot.metadata["image_copies"] = image_count
        slot.metadata["image_copy_bounds"] = deepcopy(image_copy_bounds or [])
        slot.metadata["source_supervised_geometry"] = True
        slot.metadata["promotion_visible"] = bool(resolved.get("promotionVisible"))
        slot.metadata["club_visible"] = bool(resolved.get("clubVisible"))
        slot.metadata["secondary_price_visible"] = bool(resolved.get("secondaryPriceVisible"))
        slot.metadata["supervised_profile"] = profile_id
        # The root preset id is deliberately never changed by variant/unit/theme.
        slot.metadata["preset_id"] = family_id
    return True


def _apply_role_overrides(page, slot, root: Rect, overrides: dict[str, Any]) -> None:
    if not overrides:
        return
    areas = dict(slot.metadata.get("role_area_nodes") or {})
    for role in ("image", "name", "unit"):
        raw = overrides.get(role)
        node = page.node(str(areas.get(role) or ""))
        if node is None or not _valid_bounds(raw):
            continue
        _set_rect(node, _absolute(root, raw))
        if role == "name":
            node.style["fit_inside_box"] = True
            node.style["v_align"] = "center"
        if role == "unit":
            node.style["fit_inside_box"] = True
            node.style["nowrap"] = True
            node.style["v_align"] = "center"

    raw_price = overrides.get("price")
    price_group = page.node(str(areas.get("price") or ""))
    if price_group is not None and _valid_bounds(raw_price):
        old = price_group.rect.normalized()
        target = _absolute(root, raw_price)
        for node_id in page.descendants(price_group.id):
            node = page.node(node_id)
            if node is not None:
                _set_rect(node, _map_rect(node.rect.normalized(), old, target))
        _set_rect(price_group, target)


def _materialize_image_copies(page, root_id: str, root: Rect, slot, extras: dict[str, Any], count: int, raw_bounds: Any) -> list[str]:
    primary = page.node(str(slot.node_by_role.get(BindingRole.IMAGE.value) or ""))
    if primary is None:
        return []
    bounds = [item for item in (raw_bounds or []) if _valid_bounds(item)] if isinstance(raw_bounds, (list, tuple)) else []
    if bounds:
        _set_rect(primary, _absolute(root, bounds[0]))
    created: list[str] = []
    extra_ids: list[str] = []
    for index in range(1, count):
        relative = bounds[index] if index < len(bounds) else (bounds[0] if bounds else [0.1, 0.2, 0.8, 0.45])
        rect = _absolute(root, relative)
        node = GraphicsNode(
            kind=NodeKind.IMAGE,
            name=f"IMAGE ROLE COPY {index + 1}",
            transform=Transform(x=rect.x, y=rect.y, width=rect.width, height=rect.height),
            binding_role=BindingRole.IMAGE,
            style=deepcopy(primary.style),
            metadata={"manual_item_slot_child": True, "quinta3_variant_node": True, "item_slot_role_area": "image_copy", "placeholder": True},
        )
        page.add_node(node, parent_id=root_id)
        extra_ids.append(node.id)
        created.append(node.id)
    if extra_ids:
        extras[BindingRole.IMAGE.value] = extra_ids
    return created


def _remove_variant_nodes(page, slot) -> None:
    for node_id in list(slot.metadata.get("quinta3_variant_nodes") or []):
        if node_id not in page.nodes:
            continue
        for child_id in reversed(list(page.descendants(node_id))):
            if child_id in page.nodes:
                page.remove_node(child_id)
        if node_id in page.nodes:
            page.remove_node(node_id)
    slot.metadata["quinta3_variant_nodes"] = []


def _add_secondary_price(page, root_id: str, root: Rect, family_id: str, variant: str, bounds: Any, extras: dict[str, Any], custom_layout: Any = None) -> list[str]:
    if not _valid_bounds(bounds):
        return []
    price_rect = _absolute(root, bounds)
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="SECONDARY PRICE AREA",
        transform=Transform(x=price_rect.x, y=price_rect.y, width=price_rect.width, height=price_rect.height),
        metadata={"manual_item_slot_child": True, "item_slot_role_area": "secondary_price", "quinta3_variant_node": True, "semantic_price_block_role": "secondary"},
    )
    page.add_node(group, parent_id=root_id)
    layout = deepcopy(custom_layout) if isinstance(custom_layout, dict) else deepcopy(_SECONDARY_COMPONENTS.get((family_id, variant)) or {})
    fallback = {"currency": [0.00, 0.28, 0.20, 0.42], "integer": [0.25, 0.00, 0.40, 1.00], "decimal": [0.68, 0.12, 0.32, 0.45], "unit": [0.78, 0.60, 0.20, 0.30]}
    layout = {key: layout.get(key, value) for key, value in fallback.items()}
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
            style={"font_family": "Anton", "font_size": size, "font_size_unit": "pt", "font_weight": 700, "fill": "#FFFFFF", "align": "center", "v_align": "center", "fit_inside_box": True, "nowrap": True},
            metadata={"manual_item_slot_child": True, "quinta3_variant_node": True, "item_slot_price_component": binding, "semantic_price_block_role": "secondary"},
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
        style={"font_family": "Anton", "font_size": 9.0, "font_size_unit": "pt", "font_weight": 700, "fill": "#FFFFFF", "align": "center", "v_align": "center", "fit_inside_box": True},
        metadata={"manual_item_slot_child": True, "quinta3_variant_node": True, "semantic_label_role": "promotion" if "PROMOTION" in name else "club_label"},
    )
    page.add_node(node, parent_id=root_id)
    return node


def _valid_bounds(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 4


def _absolute(parent: Rect, relative: Any) -> Rect:
    x, y, width, height = (float(value) for value in relative)
    return Rect(parent.x + x * parent.width, parent.y + y * parent.height, max(1.0, width * parent.width), max(1.0, height * parent.height))


def _map_rect(child: Rect, old: Rect, new: Rect) -> Rect:
    return Rect(new.x + ((child.x - old.x) / max(old.width, 1e-9)) * new.width, new.y + ((child.y - old.y) / max(old.height, 1e-9)) * new.height, (child.width / max(old.width, 1e-9)) * new.width, (child.height / max(old.height, 1e-9)) * new.height)


def _set_rect(node: GraphicsNode, rect: Rect) -> None:
    node.transform.x = rect.x
    node.transform.y = rect.y
    node.transform.width = max(1.0, rect.width)
    node.transform.height = max(1.0, rect.height)
