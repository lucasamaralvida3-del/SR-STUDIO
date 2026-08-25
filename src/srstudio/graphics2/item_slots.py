from __future__ import annotations

"""Manual ItemSlot presets for the Graphics2 flyer editor.

This module deliberately does not participate in Smart Slot detection.  It
builds explicit, user-created product components from ordinary SR Scene nodes
and a SmartSlot binding contract so the existing editor, drag/drop and package
persistence paths can be reused without changing renderer semantics.
"""

from dataclasses import dataclass
from typing import Any
import copy

from .model import BindingRole, GraphicsNode, NodeKind, Rect, SmartSlot, Transform, _id
from .operations import GraphicsSession, _price_parts

ITEM_SLOT_SOURCE = "manual-item-slot"
CUSTOM_PRESETS_KEY = "manual_item_slot_presets"


@dataclass(frozen=True, slots=True)
class ItemSlotPreset:
    id: str
    name: str
    width: float
    height: float
    roles: dict[str, dict[str, Any]]
    background: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "roles": copy.deepcopy(self.roles),
            "background": copy.deepcopy(self.background),
        }


def _text_role(x: float, y: float, w: float, h: float, *, size: float, weight: int = 700, align: str = "center") -> dict[str, Any]:
    return {
        "bounds": [x, y, w, h],
        "style": {
            "font_family": "Segoe UI",
            "font_size": size,
            "font_size_unit": "pt",
            "font_weight": weight,
            "align": align,
            "v_align": "center",
            "fit_inside_box": True,
        },
    }


def _builtins() -> dict[str, ItemSlotPreset]:
    return {
        "destaque": ItemSlotPreset(
            id="destaque",
            name="DESTAQUE",
            width=380,
            height=470,
            roles={
                "image": {"bounds": [0.08, 0.08, 0.84, 0.50], "style": {"fit": "contain"}},
                "name": _text_role(0.08, 0.59, 0.84, 0.11, size=21),
                "price": {"bounds": [0.10, 0.71, 0.66, 0.19]},
                "currency": _text_role(0.00, 0.22, 0.18, 0.45, size=15),
                "integer": _text_role(0.15, 0.00, 0.57, 0.88, size=50),
                "decimal": _text_role(0.68, 0.05, 0.32, 0.45, size=23),
                "unit": _text_role(0.77, 0.76, 0.20, 0.12, size=13),
            },
        ),
        "simples": ItemSlotPreset(
            id="simples",
            name="SIMPLES",
            width=300,
            height=350,
            roles={
                "name": _text_role(0.07, 0.05, 0.86, 0.13, size=17),
                "image": {"bounds": [0.10, 0.20, 0.80, 0.46], "style": {"fit": "contain"}},
                "price": {"bounds": [0.09, 0.69, 0.70, 0.22]},
                "currency": _text_role(0.00, 0.24, 0.18, 0.42, size=13),
                "integer": _text_role(0.14, 0.00, 0.58, 0.90, size=39),
                "decimal": _text_role(0.68, 0.05, 0.32, 0.46, size=19),
                "unit": _text_role(0.78, 0.77, 0.18, 0.11, size=11),
            },
        ),
        "card": ItemSlotPreset(
            id="card",
            name="CARD PREÇO SOBREPOSTO",
            width=330,
            height=390,
            background={"fill": "#FFFFFF", "stroke": "#D9E2EF", "stroke_width": 1.0, "radius_ratio": 0.055},
            roles={
                "name": _text_role(0.08, 0.06, 0.84, 0.13, size=17),
                "image": {"bounds": [0.08, 0.20, 0.84, 0.56], "style": {"fit": "contain"}},
                "price": {"bounds": [0.37, 0.70, 0.55, 0.22], "background": {"fill": "#FFFFFF", "stroke": "#D9E2EF", "stroke_width": 1.0, "radius_ratio": 0.12}},
                "currency": _text_role(0.00, 0.25, 0.19, 0.40, size=12),
                "integer": _text_role(0.15, 0.00, 0.57, 0.90, size=37),
                "decimal": _text_role(0.68, 0.06, 0.32, 0.44, size=18),
                "unit": _text_role(0.75, 0.78, 0.19, 0.10, size=10),
            },
        ),
    }


def list_item_slot_presets(document=None) -> list[dict[str, Any]]:
    presets = {key: value.to_dict() for key, value in _builtins().items()}
    if document is not None:
        custom = document.metadata.get(CUSTOM_PRESETS_KEY)
        if isinstance(custom, dict):
            for preset_id, raw in custom.items():
                if isinstance(raw, dict):
                    presets[str(preset_id)] = copy.deepcopy(raw)
    return [presets[key] for key in sorted(presets, key=lambda item: (0 if item in _builtins() else 1, item))]


def _preset(document, preset_id: str) -> dict[str, Any]:
    key = str(preset_id or "simples").strip().lower()
    builtins = _builtins()
    if key in builtins:
        return builtins[key].to_dict()
    custom = document.metadata.get(CUSTOM_PRESETS_KEY)
    if isinstance(custom, dict) and isinstance(custom.get(key), dict):
        return copy.deepcopy(custom[key])
    raise KeyError(f"Preset de ItemSlot inexistente: {preset_id}")


def _absolute(parent: Rect, relative: list[float]) -> Rect:
    x, y, w, h = (float(value) for value in relative)
    return Rect(parent.x + x * parent.width, parent.y + y * parent.height, w * parent.width, h * parent.height)


def _relative(child: Rect, parent: Rect) -> list[float]:
    return [
        (child.x - parent.x) / max(parent.width, 1e-6),
        (child.y - parent.y) / max(parent.height, 1e-6),
        child.width / max(parent.width, 1e-6),
        child.height / max(parent.height, 1e-6),
    ]


def _add_node(page, node: GraphicsNode, parent_id: str) -> GraphicsNode:
    page.add_node(node, parent_id=parent_id)
    return node


def _make_text(page, parent_id: str, name: str, text: str, bounds: Rect, style: dict[str, Any], role: BindingRole | None = None) -> GraphicsNode:
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        transform=Transform(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height),
        z_index=20,
        binding_role=role,
        style=copy.deepcopy(style),
        metadata={"manual_item_slot_child": True},
    )
    return _add_node(page, node, parent_id)


def create_item_slot(session: GraphicsSession, preset_id: str, *, x: float | None = None, y: float | None = None) -> SmartSlot:
    preset = _preset(session.document, preset_id)
    page = session.page
    width = float(preset.get("width") or 300.0)
    height = float(preset.get("height") or 350.0)
    px = float(x) if x is not None else max(12.0, (page.width - width) / 2.0)
    py = float(y) if y is not None else max(12.0, (page.height - height) / 2.0)
    root_rect = Rect(px, py, width, height)
    roles = dict(preset.get("roles") or {})

    with session.transaction("Adicionar Slot de Item"):
        root = GraphicsNode(
            kind=NodeKind.GROUP,
            name=f"ItemSlot · {preset.get('name') or preset_id}",
            transform=Transform(x=px, y=py, width=width, height=height),
            metadata={
                "manual_item_slot_root": True,
                "preset_id": str(preset.get("id") or preset_id),
                "item_slot_version": 1,
            },
        )
        page.add_node(root)

        background_style = preset.get("background")
        background_id = ""
        if isinstance(background_style, dict):
            background = GraphicsNode(
                kind=NodeKind.RECT,
                name="ItemSlot Background",
                transform=Transform(x=px, y=py, width=width, height=height),
                z_index=-30,
                style=copy.deepcopy(background_style),
                metadata={"manual_item_slot_child": True, "item_slot_background": True},
            )
            _add_node(page, background, root.id)
            background_id = background.id

        decoration_ids: list[str] = []
        raw_decorations = dict(preset.get("metadata") or {}).get("decorations")
        if isinstance(raw_decorations, list):
            for index, raw in enumerate(raw_decorations):
                if not isinstance(raw, dict):
                    continue
                try:
                    kind = NodeKind(str(raw.get("kind") or "rect"))
                except ValueError:
                    continue
                bounds = raw.get("bounds")
                if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
                    continue
                decoration_rect = _absolute(root_rect, list(bounds))
                decoration = GraphicsNode(
                    kind=kind,
                    name=str(raw.get("name") or f"SLOT DECORATION {index + 1}"),
                    transform=Transform(
                        x=decoration_rect.x,
                        y=decoration_rect.y,
                        width=decoration_rect.width,
                        height=decoration_rect.height,
                    ),
                    z_index=int(raw.get("z_index") or -20),
                    style=copy.deepcopy(raw.get("style") or {}),
                    metadata={
                        **copy.deepcopy(raw.get("metadata") or {}),
                        "manual_item_slot_child": True,
                        "item_slot_decoration": True,
                        "decoration_index": index,
                    },
                )
                if kind is NodeKind.IMAGE:
                    from .package import register_local_asset
                    from .slot_family_inventory import cached_slot_asset_path

                    asset_path = cached_slot_asset_path(
                        str(raw.get("asset_basename") or ""),
                        str(raw.get("asset_sha256") or ""),
                    )
                    if asset_path is None:
                        continue
                    asset = register_local_asset(session.document, asset_path, kind="image")
                    decoration.asset_id = asset.id
                    decoration.metadata["bound_image_source"] = str(asset_path)
                    decoration.metadata["slot_decoration_asset_sha256"] = str(raw.get("asset_sha256") or "")
                _add_node(page, decoration, root.id)
                decoration_ids.append(decoration.id)

        image_spec = dict(roles.get("image") or {})
        image_rect = _absolute(root_rect, list(image_spec.get("bounds") or [0.1, 0.2, 0.8, 0.45]))
        image_backplate_id = ""
        if dict(preset.get("metadata") or {}).get("image_backplate", True) is not False:
            image_backplate = GraphicsNode(
                kind=NodeKind.RECT,
                name="IMAGE AREA",
                transform=Transform(x=image_rect.x, y=image_rect.y, width=image_rect.width, height=image_rect.height),
                z_index=-10,
                style={"fill": "#F8FAFC", "stroke": "#CBD5E1", "stroke_width": 1.0, "radius_ratio": 0.04},
                metadata={"manual_item_slot_child": True, "item_slot_image_backplate": True},
            )
            _add_node(page, image_backplate, root.id)
            image_backplate_id = image_backplate.id
        image = GraphicsNode(
            kind=NodeKind.IMAGE,
            name="IMAGE ROLE",
            transform=Transform(x=image_rect.x, y=image_rect.y, width=image_rect.width, height=image_rect.height),
            z_index=0,
            binding_role=BindingRole.IMAGE,
            style=copy.deepcopy(image_spec.get("style") or {"fit": "contain"}),
            metadata={"manual_item_slot_child": True, "item_slot_role_area": "image", "placeholder": True},
        )
        _add_node(page, image, root.id)

        name_spec = dict(roles.get("name") or {})
        name_rect = _absolute(root_rect, list(name_spec.get("bounds") or [0.08, 0.05, 0.84, 0.13]))
        name_node = _make_text(
            page, root.id, "NAME ROLE", "NOME DO PRODUTO", name_rect,
            dict(name_spec.get("style") or {}), BindingRole.NAME,
        )
        name_node.metadata["item_slot_role_area"] = "name"

        price_spec = dict(roles.get("price") or {})
        price_rect = _absolute(root_rect, list(price_spec.get("bounds") or [0.1, 0.7, 0.68, 0.2]))
        price_group = GraphicsNode(
            kind=NodeKind.GROUP,
            name="PRICE AREA",
            transform=Transform(x=price_rect.x, y=price_rect.y, width=price_rect.width, height=price_rect.height),
            z_index=10,
            metadata={"manual_item_slot_child": True, "item_slot_role_area": "price"},
        )
        _add_node(page, price_group, root.id)
        price_background_id = ""
        if isinstance(price_spec.get("background"), dict):
            price_bg = GraphicsNode(
                kind=NodeKind.RECT,
                name="PRICE BACKGROUND",
                transform=Transform(x=price_rect.x, y=price_rect.y, width=price_rect.width, height=price_rect.height),
                z_index=-10,
                style=copy.deepcopy(price_spec["background"]),
                metadata={"manual_item_slot_child": True, "item_slot_price_background": True},
            )
            _add_node(page, price_bg, price_group.id)
            price_background_id = price_bg.id

        component_nodes: dict[str, GraphicsNode] = {}
        component_defs = (
            ("currency", "R$", BindingRole.CURRENCY, "CURRENCY"),
            ("integer", "00", BindingRole.PRICE_REAIS, "INTEGER"),
            ("decimal", ",00", BindingRole.PRICE_CENTS, "DECIMAL"),
        )
        for key, placeholder, binding, label in component_defs:
            spec = dict(roles.get(key) or {})
            component_rect = _absolute(price_rect, list(spec.get("bounds") or [0, 0, 1, 1]))
            node = _make_text(page, price_group.id, f"PRICE {label}", placeholder, component_rect, dict(spec.get("style") or {}), binding)
            node.metadata["item_slot_price_component"] = key
            component_nodes[key] = node

        unit_spec = dict(roles.get("unit") or {})
        unit_rect = _absolute(root_rect, list(unit_spec.get("bounds") or [0.78, 0.8, 0.18, 0.1]))
        unit = _make_text(page, root.id, "UNIT ROLE", "UN", unit_rect, dict(unit_spec.get("style") or {}), BindingRole.UNIT)
        unit.metadata["item_slot_role_area"] = "unit"

        slot = SmartSlot(
            id=_id("slot"),
            name=str(preset.get("name") or "Item Slot"),
            page_id=page.id,
            node_by_role={
                BindingRole.IMAGE.value: image.id,
                BindingRole.NAME.value: name_node.id,
                BindingRole.CURRENCY.value: component_nodes["currency"].id,
                BindingRole.PRICE_REAIS.value: component_nodes["integer"].id,
                BindingRole.PRICE_CENTS.value: component_nodes["decimal"].id,
                BindingRole.UNIT.value: unit.id,
            },
            confidence=1.0,
            metadata={
                "source": ITEM_SLOT_SOURCE,
                "manual_item_slot": True,
                "preset_id": str(preset.get("id") or preset_id),
                "root_node_id": root.id,
                "role_area_nodes": {"image": image.id, "name": name_node.id, "price": price_group.id, "unit": unit.id},
                "decorative_nodes": [
                    item
                    for item in (background_id, *decoration_ids, image_backplate_id, price_background_id)
                    if item
                ],
                "price_block": {
                    "currency_node": component_nodes["currency"].id,
                    "integer_node": component_nodes["integer"].id,
                    "decimal_node": component_nodes["decimal"].id,
                    "unit_node": unit.id,
                    "combined_value": "",
                },
                "state": "empty",
                "product_snapshot": {},
            },
        )
        root.metadata["item_slot_id"] = slot.id
        page.slots[slot.id] = slot

    session.selection = {root.id}
    session.anchor_id = root.id
    refresh_item_slot_metadata(page, slot)
    return slot


def is_manual_item_slot(slot: SmartSlot | None) -> bool:
    return bool(slot and slot.metadata.get("manual_item_slot") and slot.metadata.get("source") == ITEM_SLOT_SOURCE)


def item_slot_for_node(page, node_id: str) -> SmartSlot | None:
    node_id = str(node_id or "")
    for slot in page.slots.values():
        if not is_manual_item_slot(slot):
            continue
        root_id = str(slot.metadata.get("root_node_id") or "")
        if node_id == root_id or node_id in page.descendants(root_id):
            return slot
    return None


def item_slot_snapshot(page, slot: SmartSlot) -> dict[str, Any]:
    root_id = str(slot.metadata.get("root_node_id") or "")
    root = page.node(root_id)
    if root is None:
        return {}
    root_rect = root.rect.normalized()
    areas = {}
    for role, node_id in dict(slot.metadata.get("role_area_nodes") or {}).items():
        node = page.node(str(node_id))
        if node is None:
            continue
        areas[str(role)] = {
            "node_id": node.id,
            "x": node.transform.x,
            "y": node.transform.y,
            "width": node.transform.width,
            "height": node.transform.height,
            "relative": _relative(node.rect.normalized(), root_rect),
        }
    return {
        "slot_id": slot.id,
        "preset_id": str(slot.metadata.get("preset_id") or ""),
        "name": slot.name,
        "root_node_id": root_id,
        "bounds": {"x": root_rect.x, "y": root_rect.y, "width": root_rect.width, "height": root_rect.height},
        "internal_roles": areas,
        "price_block": copy.deepcopy(slot.metadata.get("price_block") or {}),
        "state": "filled" if slot.product_id else "empty",
        "product_id": slot.product_id,
        "slot_kind": "multi_item_root" if slot.metadata.get("multi_item_slot_root") else ("product_cell" if slot.metadata.get("multi_item_product_cell") else "single_item"),
        "product_cell_index": int(slot.metadata.get("product_cell_index") or 0),
        "product_cell_count": int(slot.metadata.get("product_cell_count") or 1),
        "multi_item_root_slot_id": str(slot.metadata.get("multi_item_root_slot_id") or ""),
    }


def list_item_slots(document) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in document.pages:
        for slot in page.slots.values():
            if is_manual_item_slot(slot):
                refresh_item_slot_metadata(page, slot)
                item = item_slot_snapshot(page, slot)
                item["page_id"] = page.id
                out.append(item)
    return out


def refresh_item_slot_metadata(page, slot: SmartSlot) -> None:
    if not is_manual_item_slot(slot):
        return
    if slot.metadata.get("multi_item_slot_root"):
        from .multi_item_slots import refresh_multi_item_metadata

        refresh_multi_item_metadata(page, slot)
        return
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if slot.metadata.get("multi_item_product_cell") and root is not None:
        rect = root.rect.normalized()
        slot.metadata["effective_bounds"] = {
            "x": rect.x,
            "y": rect.y,
            "width": rect.width,
            "height": rect.height,
        }
    price = slot.metadata.setdefault("price_block", {})
    integer = page.node(str(price.get("integer_node") or ""))
    decimal = page.node(str(price.get("decimal_node") or ""))
    if slot.product_id and integer is not None and decimal is not None:
        raw_decimal = str(decimal.text or "").strip().replace(",", ".")
        try:
            price["combined_value"] = f"{int(str(integer.text).strip())}{float(raw_decimal):.2f}"[0:0]
        except (TypeError, ValueError):
            price["combined_value"] = ""
        # Compose without locale ambiguity while preserving the split text nodes.
        whole = str(integer.text or "").strip()
        cents = str(decimal.text or "").strip().lstrip(",.")
        price["combined_value"] = f"{whole}.{cents}" if whole and cents else ""
    else:
        price["combined_value"] = ""
    slot.metadata["state"] = "filled" if slot.product_id else "empty"


def refresh_all_item_slots(document) -> None:
    for page in document.pages:
        for slot in page.slots.values():
            refresh_item_slot_metadata(page, slot)


def set_item_slot_role_bounds(
    session: GraphicsSession,
    slot_id: str,
    role: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
) -> bool:
    slot = session.page.slots.get(str(slot_id))
    if not is_manual_item_slot(slot):
        return False
    key = str(role or "").strip().lower()
    node_id = str(dict(slot.metadata.get("role_area_nodes") or {}).get(key) or "")
    node = session.page.node(node_id)
    if node is None:
        return False
    session.resize_node(node.id, x=float(x), y=float(y), width=max(1.0, float(width)), height=max(1.0, float(height)))
    return True


def _reset_clone_content(page, slot: SmartSlot) -> None:
    slot.product_id = ""
    slot.metadata["product_snapshot"] = {}
    slot.metadata["state"] = "empty"
    placeholders = {
        BindingRole.NAME.value: "NOME DO PRODUTO",
        BindingRole.CURRENCY.value: "R$",
        BindingRole.PRICE_REAIS.value: "00",
        BindingRole.PRICE_CENTS.value: ",00",
        BindingRole.UNIT.value: "UN",
    }
    for role, node_id in slot.node_by_role.items():
        node = page.node(str(node_id))
        if node is None:
            continue
        if role == BindingRole.IMAGE.value:
            node.asset_id = ""
            node.metadata.pop("bound_image_source", None)
            node.metadata["placeholder"] = True
        elif role in placeholders and node.kind is NodeKind.TEXT:
            node.text = placeholders[role]
    refresh_item_slot_metadata(page, slot)


def duplicate_item_slot(session: GraphicsSession, slot_id: str, *, dx: float = 20.0, dy: float = 20.0, include_product: bool = False) -> SmartSlot:
    source_slot = session.page.slots.get(str(slot_id))
    if not is_manual_item_slot(source_slot):
        raise KeyError(f"ItemSlot inexistente: {slot_id}")
    root_id = str(source_slot.metadata.get("root_node_id") or "")
    if session.page.node(root_id) is None:
        raise KeyError(f"Raiz do ItemSlot inexistente: {root_id}")

    page = session.page
    mapping: dict[str, str] = {}
    with session.transaction("Duplicar Slot de Item"):
        session._duplicate_tree(root_id, None, float(dx), float(dy), mapping)
        clone = copy.deepcopy(source_slot)
        clone.id = _id("slot")
        clone.page_id = page.id
        clone.node_by_role = {role: mapping[node_id] for role, node_id in source_slot.node_by_role.items() if node_id in mapping}
        clone.metadata = copy.deepcopy(source_slot.metadata)
        clone.metadata["root_node_id"] = mapping[root_id]
        clone.metadata["duplicated_from_slot_id"] = source_slot.id
        clone.metadata["role_area_nodes"] = {
            role: mapping[node_id]
            for role, node_id in dict(source_slot.metadata.get("role_area_nodes") or {}).items()
            if node_id in mapping
        }
        clone.metadata["decorative_nodes"] = [mapping[node_id] for node_id in source_slot.metadata.get("decorative_nodes") or [] if node_id in mapping]
        price = copy.deepcopy(source_slot.metadata.get("price_block") or {})
        for key in ("currency_node", "integer_node", "decimal_node", "unit_node"):
            old = str(price.get(key) or "")
            price[key] = mapping.get(old, "")
        clone.metadata["price_block"] = price
        clone_root = page.node(mapping[root_id])
        if clone_root is not None:
            clone_root.metadata["item_slot_id"] = clone.id
        page.slots[clone.id] = clone
        if not include_product:
            _reset_clone_content(page, clone)

    session.selection = {mapping[root_id]}
    session.anchor_id = mapping[root_id]
    return clone


def save_item_slot_as_preset(session: GraphicsSession, slot_id: str, name: str) -> dict[str, Any]:
    slot = session.page.slots.get(str(slot_id))
    if not is_manual_item_slot(slot):
        raise KeyError(f"ItemSlot inexistente: {slot_id}")
    page = session.page
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        raise KeyError("Raiz do ItemSlot inexistente.")
    title = " ".join(str(name or "").split()).strip() or "MODELO PERSONALIZADO"
    preset_id = "custom-" + _id("preset").split("_", 1)[-1]
    root_rect = root.rect.normalized()
    areas = dict(slot.metadata.get("role_area_nodes") or {})

    def role_spec(role: str) -> dict[str, Any]:
        node = page.node(str(areas.get(role) or ""))
        return {"bounds": _relative(node.rect.normalized(), root_rect)} if node is not None else {}

    preset: dict[str, Any] = {
        "id": preset_id,
        "name": title,
        "width": root_rect.width,
        "height": root_rect.height,
        "roles": {
            "image": role_spec("image"),
            "name": role_spec("name"),
            "price": role_spec("price"),
            "unit": role_spec("unit"),
        },
    }
    for role, binding in (
        ("image", BindingRole.IMAGE.value),
        ("name", BindingRole.NAME.value),
        ("unit", BindingRole.UNIT.value),
    ):
        node = page.node(slot.node_by_role.get(binding, ""))
        if node is not None:
            preset["roles"][role]["style"] = copy.deepcopy(node.style)
    price_group = page.node(str(areas.get("price") or ""))
    price_rect = price_group.rect.normalized() if price_group is not None else root_rect
    for role, binding in (
        ("currency", BindingRole.CURRENCY.value),
        ("integer", BindingRole.PRICE_REAIS.value),
        ("decimal", BindingRole.PRICE_CENTS.value),
    ):
        node = page.node(slot.node_by_role.get(binding, ""))
        if node is not None:
            preset["roles"][role] = {"bounds": _relative(node.rect.normalized(), price_rect), "style": copy.deepcopy(node.style)}

    root_background = next(
        (page.node(node_id) for node_id in slot.metadata.get("decorative_nodes") or [] if page.node(node_id) is not None and page.node(node_id).metadata.get("item_slot_background")),
        None,
    )
    if root_background is not None:
        preset["background"] = copy.deepcopy(root_background.style)
    price_background = next(
        (page.node(node_id) for node_id in slot.metadata.get("decorative_nodes") or [] if page.node(node_id) is not None and page.node(node_id).metadata.get("item_slot_price_background")),
        None,
    )
    if price_background is not None:
        preset["roles"]["price"]["background"] = copy.deepcopy(price_background.style)

    with session.transaction("Salvar Slot como Modelo"):
        custom = session.document.metadata.setdefault(CUSTOM_PRESETS_KEY, {})
        if not isinstance(custom, dict):
            custom = {}
            session.document.metadata[CUSTOM_PRESETS_KEY] = custom
        custom[preset_id] = copy.deepcopy(preset)
    return preset


def bind_product_to_item_slot(session: GraphicsSession, slot_id: str, product: dict[str, Any]) -> bool:
    slot = session.page.slots.get(str(slot_id))
    if not is_manual_item_slot(slot):
        return False
    session.bind_product(slot.id, product)
    for node_id in slot.node_by_role.values():
        node = session.page.node(node_id)
        if node is not None and node.binding_role is BindingRole.IMAGE and slot.product_id:
            node.metadata["placeholder"] = False
    refresh_item_slot_metadata(session.page, slot)
    return True
