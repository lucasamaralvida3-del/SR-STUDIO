from __future__ import annotations

"""Reusable MultiItemSlotRoot + independent ProductCell runtime."""

from copy import deepcopy
from typing import Any

from .item_slots import ITEM_SLOT_SOURCE, bind_product_to_item_slot, refresh_item_slot_metadata
from .model import BindingRole, GraphicsNode, NodeKind, Rect, SmartSlot, Transform, _id
from .operations import GraphicsSession
from .slot_corpus_full_card import MEAT_STRIP_SOURCE_STRIP_FILL, _strip_segment_path
from .slot_family_inventory import multi_item_family_ids, slot_family_entry, slot_font_family


MULTI_ITEM_ROOT_VERSION = 1


_CELL_LAYOUTS: dict[str, dict[str, Any]] = {
    "quinta3-meat-strip": {
        "image": [0.04, 0.12, 0.92, 0.64],
        "name": [0.05, 0.00, 0.90, 0.17],
        "price": [0.22, 0.74, 0.58, 0.25],
        "unit": [0.72, 0.89, 0.16, 0.09],
        "foreground": "#FFFFFF",
        "secondary": False,
    },
    "quinta3-compact-blue-strip": {
        "image": [0.03, 0.00, 0.58, 0.66],
        "name": [0.03, 0.65, 0.49, 0.25],
        "price": [0.53, 0.56, 0.43, 0.39],
        "unit": [0.84, 0.88, 0.12, 0.08],
        "foreground": "#FFFFFF",
        "secondary": True,
    },
    "quinta3-compact-beige-strip": {
        "image": [0.02, 0.00, 0.58, 0.66],
        "name": [0.03, 0.66, 0.48, 0.22],
        "price": [0.52, 0.55, 0.44, 0.40],
        "unit": [0.84, 0.87, 0.12, 0.09],
        "foreground": "#FFFFFF",
        "secondary": True,
    },
}

_COMPACT_SOURCE_PROFILES = {
    "quinta3-compact-blue-strip": ("bom-bril", "odor-boom", "pano", "rodo"),
    "quinta3-compact-beige-strip": ("molho", "banha", "canjica"),
}


def is_multi_item_root(slot: SmartSlot | None) -> bool:
    return bool(slot and slot.metadata.get("multi_item_slot_root"))


def is_product_cell(slot: SmartSlot | None) -> bool:
    return bool(slot and slot.metadata.get("multi_item_product_cell"))


def create_multi_item_slot(
    session: GraphicsSession,
    family_id: str,
    *,
    x: float | None = None,
    y: float | None = None,
) -> SmartSlot:
    family_id = str(family_id or "").strip()
    if family_id not in set(multi_item_family_ids()):
        raise KeyError(f"Família multi-item inexistente: {family_id}")
    if family_id == "quinta3-meat-strip":
        return _create_certified_meat_strip(session, x=x, y=y)
    entry = slot_family_entry(family_id)
    preset = entry["INTERNAL_PRESET"]
    font_family = slot_font_family(session.document)
    count = int(entry["PRODUCT_CELL_COUNT"])
    page = session.page
    width = float(preset["width"])
    height = float(preset["height"])
    px = float(x) if x is not None else max(12.0, (page.width - width) / 2.0)
    py = float(y) if y is not None else max(12.0, (page.height - height) / 2.0)
    root_rect = Rect(px, py, width, height)
    root_slot_id = _id("slot")

    with session.transaction("Adicionar Slot Multi-item"):
        root = GraphicsNode(
            kind=NodeKind.GROUP,
            name=f"MultiItemSlotRoot · {entry['CATALOG_NAME']}",
            transform=Transform(x=px, y=py, width=width, height=height),
            metadata={
                "manual_item_slot_root": True,
                "multi_item_slot_root": True,
                "multi_item_slot_version": MULTI_ITEM_ROOT_VERSION,
                "item_slot_id": root_slot_id,
                "preset_id": family_id,
                "ownership_kind": "multi_item_root",
            },
        )
        page.add_node(root)
        shared_nodes = _add_shared_visuals(page, root, root_rect, family_id, count, preset)

        cell_slots: list[SmartSlot] = []
        cell_roots: list[str] = []
        cell_width = width / count
        for index in range(count):
            cell_rect = Rect(px + index * cell_width, py, cell_width, height)
            cell = _create_product_cell(
                page,
                parent_id=root.id,
                root_slot_id=root_slot_id,
                family_id=family_id,
                catalog_name=str(entry["CATALOG_NAME"]),
                index=index,
                rect=cell_rect,
                font_family=font_family,
            )
            page.slots[cell.id] = cell
            cell_slots.append(cell)
            cell_roots.append(str(cell.metadata["root_node_id"]))

        root_slot = SmartSlot(
            id=root_slot_id,
            name=str(entry["CATALOG_NAME"]),
            page_id=page.id,
            node_by_role={"container": root.id},
            confidence=1.0,
            metadata={
                "source": ITEM_SLOT_SOURCE,
                "manual_item_slot": True,
                "multi_item_slot_root": True,
                "multi_item_slot_version": MULTI_ITEM_ROOT_VERSION,
                "preset_id": family_id,
                "quinta3_family": family_id,
                "root_node_id": root.id,
                "product_cell_slot_ids": [slot.id for slot in cell_slots],
                "product_cell_root_node_ids": cell_roots,
                "product_cell_count": count,
                "shared_visual_nodes": shared_nodes,
                "state": "empty",
                "product_snapshot": {},
                "category_is_not_family": True,
                "product_identity_is_not_family": True,
            },
        )
        page.slots[root_slot.id] = root_slot
        for node_id in shared_nodes:
            node = page.node(node_id)
            if node is not None:
                node.metadata["multi_item_owner_slot_id"] = root_slot.id
        validate_multi_item_ownership(page, root_slot)

    session.selection = {root.id}
    session.anchor_id = root.id
    refresh_multi_item_metadata(page, root_slot)
    return root_slot


def _create_certified_meat_strip(
    session: GraphicsSession,
    *,
    x: float | None = None,
    y: float | None = None,
) -> SmartSlot:
    """Wrap the certified Meat Strip cells in the public multi-item root.

    The existing full-card/ownership runtime is the visual oracle for this
    family.  Reusing it here prevents a catalog/UX improvement from changing
    its crop, source geometry, Anton roles or PriceBlock topology.
    """

    from .slot_corpus_meat_strip_ownership import (
        PROFILE_ORDER,
        normalize_meat_strip_ownership,
        strip_ownership_snapshot,
    )
    from .slot_corpus_variant_runtime import create_quinta3_item_slot

    page = session.page
    cells: list[SmartSlot] = []
    for index, profile_id in enumerate(PROFILE_ORDER):
        cell = create_quinta3_item_slot(
            session,
            "quinta3-meat-strip",
            variant="default",
            parameters={"supervisedProfile": profile_id},
            x=x,
            y=y,
        )
        with session.transaction("Normalizar ProductCell Meat Strip"):
            normalize_meat_strip_ownership(page, cell, profile_id=profile_id)
        cells.append(cell)

    strip_root_id = str(cells[0].metadata["meat_strip_root_id"])
    strip_root = page.node(strip_root_id)
    if strip_root is None:
        raise RuntimeError("MeatStripRoot certificado não foi materializado.")

    root_slot_id = _id("slot")
    shared_nodes = list(strip_ownership_snapshot(page, strip_root_id)["shared_visual_nodes"])
    for index, cell in enumerate(cells):
        cell.metadata.update(
            {
                "multi_item_product_cell": True,
                "multi_item_root_slot_id": root_slot_id,
                "multi_item_root_node_id": strip_root_id,
                "product_cell_index": index,
                "product_cell_count": len(cells),
                "category_is_not_family": True,
                "product_identity_is_not_family": True,
            }
        )
        cell_root = page.node(str(cell.metadata.get("root_node_id") or ""))
        if cell_root is not None:
            cell_root.metadata.update(
                {
                    "multi_item_product_cell": True,
                    "multi_item_root_slot_id": root_slot_id,
                    "product_cell_index": index,
                }
            )

    strip_root.metadata.update(
        {
            "manual_item_slot_root": True,
            "multi_item_slot_root": True,
            "multi_item_slot_version": MULTI_ITEM_ROOT_VERSION,
            "item_slot_id": root_slot_id,
            "preset_id": "quinta3-meat-strip",
            "ownership_kind": "multi_item_root",
        }
    )
    root_slot = SmartSlot(
        id=root_slot_id,
        name="FAIXA VINHO · 4 ITENS",
        page_id=page.id,
        node_by_role={"container": strip_root_id},
        confidence=1.0,
        metadata={
            "source": ITEM_SLOT_SOURCE,
            "manual_item_slot": True,
            "multi_item_slot_root": True,
            "multi_item_slot_version": MULTI_ITEM_ROOT_VERSION,
            "preset_id": "quinta3-meat-strip",
            "quinta3_family": "quinta3-meat-strip",
            "root_node_id": strip_root_id,
            "product_cell_slot_ids": [cell.id for cell in cells],
            "product_cell_root_node_ids": [str(cell.metadata["root_node_id"]) for cell in cells],
            "product_cell_count": len(cells),
            "shared_visual_nodes": shared_nodes,
            "state": "empty",
            "product_snapshot": {},
            "category_is_not_family": True,
            "product_identity_is_not_family": True,
        },
    )
    page.slots[root_slot.id] = root_slot
    for node_id in shared_nodes:
        node = page.node(str(node_id))
        if node is not None:
            node.metadata["multi_item_owner_slot_id"] = root_slot.id
    validate_multi_item_ownership(page, root_slot)
    session.selection = {strip_root_id}
    session.anchor_id = strip_root_id
    refresh_multi_item_metadata(page, root_slot)
    return root_slot


def _create_product_cell(
    page,
    *,
    parent_id: str,
    root_slot_id: str,
    family_id: str,
    catalog_name: str,
    index: int,
    rect: Rect,
    font_family: str,
) -> SmartSlot:
    layout = _cell_layout(family_id, index)
    cell_slot_id = _id("slot")
    root = GraphicsNode(
        kind=NodeKind.GROUP,
        name=f"ProductCell {index + 1}",
        transform=Transform(x=rect.x, y=rect.y, width=rect.width, height=rect.height),
        metadata={
            "manual_item_slot_root": True,
            "multi_item_product_cell": True,
            "multi_item_root_slot_id": root_slot_id,
            "product_cell_index": index,
            "item_slot_id": cell_slot_id,
            "ownership_kind": "product_cell",
        },
    )
    page.add_node(root, parent_id=parent_id)

    image_rect = _absolute(rect, layout["image"])
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name=f"CELL {index + 1} · IMAGE",
        transform=_transform(image_rect),
        binding_role=BindingRole.IMAGE,
        style={"fit": "contain", "crop": {}, "fill_rect": {}, "clip": True, "zoom": 1.0, "focus_x": 0.5, "focus_y": 0.5},
        metadata=_cell_metadata(root_slot_id, cell_slot_id, index, "image", placeholder=True),
    )
    page.add_node(image, parent_id=root.id)

    image_copy_ids: list[str] = []
    for copy_index, copy_bounds in enumerate(list(layout.get("image_copy_bounds") or [])[1:], start=2):
        copy = GraphicsNode(
            kind=NodeKind.IMAGE,
            name=f"CELL {index + 1} · IMAGE COPY {copy_index}",
            transform=_transform(_absolute(rect, copy_bounds)),
            binding_role=BindingRole.IMAGE,
            style=deepcopy(image.style),
            metadata=_cell_metadata(root_slot_id, cell_slot_id, index, "image_copy", placeholder=True),
        )
        page.add_node(copy, parent_id=root.id)
        image_copy_ids.append(copy.id)

    name_rect = _absolute(rect, layout["name"])
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        name=f"CELL {index + 1} · NAME",
        text="NOME DO PRODUTO",
        transform=_transform(name_rect),
        binding_role=BindingRole.NAME,
        style=_text_style(10.0 if family_id == "quinta3-meat-strip" else 7.5, layout["foreground"], wrap=True, font_family=font_family),
        metadata=_cell_metadata(root_slot_id, cell_slot_id, index, "name"),
    )
    page.add_node(name, parent_id=root.id)

    price_rect = _absolute(rect, layout["price"])
    price_group = GraphicsNode(
        kind=NodeKind.GROUP,
        name=f"CELL {index + 1} · PRICEBLOCK",
        transform=_transform(price_rect),
        metadata=_cell_metadata(root_slot_id, cell_slot_id, index, "priceblock"),
    )
    page.add_node(price_group, parent_id=root.id)
    price_nodes: dict[str, GraphicsNode] = {}
    specs = (
        ("currency", BindingRole.CURRENCY, "R$", [0.00, 0.32, 0.20, 0.34], 7.0),
        ("integer", BindingRole.PRICE_REAIS, "00", [0.19, 0.00, 0.54, 1.00], 24.0),
        ("decimal", BindingRole.PRICE_CENTS, ",00", [0.72, 0.08, 0.28, 0.42], 9.0),
    )
    for role, binding, placeholder, bounds, size in specs:
        node = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"CELL {index + 1} · {role.upper()}",
            text=placeholder,
            transform=_transform(_absolute(price_rect, bounds)),
            binding_role=binding,
            style=_text_style(size, layout["foreground"], wrap=False, font_family=font_family),
            metadata=_cell_metadata(root_slot_id, cell_slot_id, index, role),
        )
        page.add_node(node, parent_id=price_group.id)
        price_nodes[role] = node

    unit = GraphicsNode(
        kind=NodeKind.TEXT,
        name=f"CELL {index + 1} · UNIT",
        text="UN",
        transform=_transform(_absolute(rect, layout["unit"])),
        binding_role=BindingRole.UNIT,
        style=_text_style(7.0, layout["foreground"], wrap=False, font_family=font_family),
        metadata=_cell_metadata(root_slot_id, cell_slot_id, index, "unit"),
    )
    page.add_node(unit, parent_id=root.id)

    extras: dict[str, list[str]] = {}
    if image_copy_ids:
        extras[BindingRole.IMAGE.value] = image_copy_ids
    if layout["secondary"]:
        secondary_group, secondary = _add_secondary_price(
            page,
            root.id,
            root_slot_id,
            cell_slot_id,
            index,
            rect,
            bounds=layout.get("secondary_bounds"),
            components=layout.get("secondary_components"),
            font_family=font_family,
        )
        extras.update(secondary)
        promo = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"CELL {index + 1} · PROMOTION",
            text="PROMOÇÃO",
            transform=_transform(_absolute(rect, layout.get("promotion_bounds") or [0.61, 0.42, 0.33, 0.10])),
            style=_text_style(5.5, "#FFFFFF", wrap=False, font_family=font_family),
            metadata=_cell_metadata(root_slot_id, cell_slot_id, index, "promotion"),
        )
        page.add_node(promo, parent_id=root.id)
        extras["promotion"] = [promo.id]
        secondary_group.metadata["semantic_price_block_role"] = "secondary"

    slot = SmartSlot(
        id=cell_slot_id,
        name=f"{catalog_name} · Célula {index + 1}",
        page_id=page.id,
        node_by_role={
            BindingRole.IMAGE.value: image.id,
            BindingRole.NAME.value: name.id,
            BindingRole.CURRENCY.value: price_nodes["currency"].id,
            BindingRole.PRICE_REAIS.value: price_nodes["integer"].id,
            BindingRole.PRICE_CENTS.value: price_nodes["decimal"].id,
            BindingRole.UNIT.value: unit.id,
        },
        confidence=1.0,
        metadata={
            "source": ITEM_SLOT_SOURCE,
            "manual_item_slot": True,
            "multi_item_product_cell": True,
            "multi_item_root_slot_id": root_slot_id,
            "multi_item_root_node_id": parent_id,
            "product_cell_index": index,
            "product_cell_count": 1,
            "preset_id": family_id,
            "quinta3_family": family_id,
            "root_node_id": root.id,
            "role_area_nodes": {"image": image.id, "name": name.id, "price": price_group.id, "unit": unit.id},
            "decorative_nodes": [],
            "extra_bindings": extras,
            "price_block": {
                "currency_node": price_nodes["currency"].id,
                "integer_node": price_nodes["integer"].id,
                "decimal_node": price_nodes["decimal"].id,
                "unit_node": unit.id,
                "combined_value": "",
            },
            "state": "empty",
            "product_snapshot": {},
            "category_is_not_family": True,
            "product_identity_is_not_family": True,
            "image_behavior": "generic-contain",
        },
    )
    return slot


def _add_secondary_price(
    page,
    parent_id: str,
    root_slot_id: str,
    cell_slot_id: str,
    index: int,
    cell: Rect,
    *,
    bounds: Any = None,
    components: Any = None,
    font_family: str = "Impact",
):
    group_rect = _absolute(cell, bounds or [0.54, 0.37, 0.40, 0.22])
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name=f"CELL {index + 1} · SECONDARY PRICEBLOCK",
        transform=_transform(group_rect),
        metadata=_cell_metadata(root_slot_id, cell_slot_id, index, "secondary_priceblock"),
    )
    page.add_node(group, parent_id=parent_id)
    extras: dict[str, list[str]] = {}
    component_layout = dict(components or {})
    specs = (
        ("app_price_currency", "R$", component_layout.get("currency") or [0.00, 0.28, 0.20, 0.40], 5.5),
        ("app_price_integer", "00", component_layout.get("integer") or [0.20, 0.00, 0.50, 1.00], 13.0),
        ("app_price_cents", ",00", component_layout.get("decimal") or [0.70, 0.10, 0.30, 0.44], 6.0),
        ("app_unit", "UN", component_layout.get("unit") or [0.78, 0.65, 0.20, 0.25], 5.0),
    )
    for role, text, bounds, size in specs:
        node = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"CELL {index + 1} · {role.upper()}",
            text=text,
            transform=_transform(_absolute(group_rect, bounds)),
            style=_text_style(size, "#FFFFFF", wrap=False, font_family=font_family),
            metadata=_cell_metadata(root_slot_id, cell_slot_id, index, role),
        )
        page.add_node(node, parent_id=group.id)
        extras[role] = [node.id]
    return group, extras


def _add_shared_visuals(page, root: GraphicsNode, rect: Rect, family_id: str, count: int, preset: dict[str, Any]) -> list[str]:
    fill = str(preset.get("metadata", {}).get("shared_fill") or "#470000")
    created: list[str] = []
    if family_id == "quinta3-meat-strip":
        background = GraphicsNode(
            kind=NodeKind.RECT,
            name="SharedVisualLayer · BLACK BACKGROUND",
            transform=_transform(rect),
            z_index=-20,
            style={"fill": "#000000", "stroke": "transparent", "stroke_width": 0.0},
            metadata={"multi_item_shared_visual": True, "ownership_kind": "shared_visual", "shared_role": "background"},
        )
        page.add_node(background, parent_id=root.id)
        created.append(background.id)
        strip_rect = Rect(rect.x, rect.y + rect.height * 0.80, rect.width, rect.height * 0.20)
        strip = GraphicsNode(
            kind=NodeKind.PATH,
            name="SharedVisualLayer · WINE STRIP",
            transform=_transform(strip_rect),
            z_index=0,
            style={"fill": MEAT_STRIP_SOURCE_STRIP_FILL, "stroke": "transparent", "stroke_width": 0.0},
            metadata={
                "multi_item_shared_visual": True,
                "ownership_kind": "shared_visual",
                "shared_role": "shared_strip",
                "source_geometry": "custGeom",
                "custom_path": _strip_segment_path(rect.width, "single"),
            },
        )
    else:
        strip_rect = Rect(rect.x, rect.y + rect.height * 0.26, rect.width, rect.height * 0.70)
        strip = GraphicsNode(
            kind=NodeKind.RECT,
            name="SharedVisualLayer · COMPACT STRIP",
            transform=_transform(strip_rect),
            z_index=-5,
            style={"fill": fill, "stroke": "transparent", "stroke_width": 0.0, "radius_ratio": 0.12},
            metadata={"multi_item_shared_visual": True, "ownership_kind": "shared_visual", "shared_role": "shared_strip"},
        )
    page.add_node(strip, parent_id=root.id)
    created.append(strip.id)
    for index in range(1, count):
        x = rect.x + rect.width * index / count
        divider = GraphicsNode(
            kind=NodeKind.LINE,
            name=f"SharedForegroundLayer · DIVIDER {index}",
            transform=Transform(x=x, y=rect.y + rect.height * 0.12, width=0.0, height=rect.height * 0.76),
            z_index=50,
            style={"stroke": fill if family_id == "quinta3-meat-strip" else "#FFFFFF", "stroke_width": 1.5},
            metadata={"multi_item_shared_visual": True, "ownership_kind": "shared_visual", "shared_role": "divider"},
        )
        page.add_node(divider, parent_id=root.id)
        created.append(divider.id)
    return created


def bind_product_to_multi_item_cell(session: GraphicsSession, slot_id: str, product: dict[str, Any]) -> bool:
    slot = session.page.slots.get(str(slot_id))
    if not is_product_cell(slot):
        return False
    before_siblings = {
        sibling.id: deepcopy(sibling.metadata.get("product_snapshot") or {})
        for sibling in product_cells_for_root(session.page, str(slot.metadata["multi_item_root_slot_id"]))
        if sibling.id != slot.id
    }
    if str(slot.metadata.get("preset_id") or "") == "quinta3-meat-strip":
        from .slot_corpus_bindings import bind_product_to_quinta3_slot

        changed = bind_product_to_quinta3_slot(session, slot.id, product)
    else:
        changed = bind_product_to_item_slot(session, slot.id, product)
    if not changed:
        return False
    unit_node = session.page.node(str(slot.node_by_role.get(BindingRole.UNIT.value) or ""))
    if unit_node is not None:
        unit_node.text = str(product.get("unit") or "UN").strip().upper().lstrip("/")
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        _bind_secondary(session.page, extras, product)
    for sibling_id, snapshot in before_siblings.items():
        sibling = session.page.slots[sibling_id]
        if sibling.metadata.get("product_snapshot") != snapshot:
            raise AssertionError("Binding de ProductCell alterou uma célula irmã.")
    root = session.page.slots.get(str(slot.metadata["multi_item_root_slot_id"]))
    if root is not None:
        refresh_multi_item_metadata(session.page, root)
    return True


def clear_multi_item_cell(session: GraphicsSession, slot_id: str) -> bool:
    slot = session.page.slots.get(str(slot_id))
    if not is_product_cell(slot):
        return False
    with session.transaction("Limpar produto da célula"):
        slot.product_id = ""
        slot.metadata["product_snapshot"] = {}
        placeholders = {
            BindingRole.NAME.value: "NOME DO PRODUTO",
            BindingRole.CURRENCY.value: "R$",
            BindingRole.PRICE_REAIS.value: "00",
            BindingRole.PRICE_CENTS.value: ",00",
            BindingRole.UNIT.value: "UN",
        }
        for role, node_id in slot.node_by_role.items():
            node = session.page.node(str(node_id))
            if node is None:
                continue
            if role == BindingRole.IMAGE.value:
                node.asset_id = ""
                node.metadata.pop("bound_image_source", None)
                node.metadata["placeholder"] = True
            elif role in placeholders and node.kind is NodeKind.TEXT:
                node.text = placeholders[role]
        extras = slot.metadata.get("extra_bindings")
        if isinstance(extras, dict):
            for key, text in {
                "app_price_currency": "R$",
                "app_price_integer": "00",
                "app_price_cents": ",00",
                "app_unit": "UN",
                "promotion": "PROMOÇÃO",
            }.items():
                _set_extra_text(session.page, extras, key, text)
        refresh_item_slot_metadata(session.page, slot)
        root = session.page.slots.get(str(slot.metadata.get("multi_item_root_slot_id") or ""))
        if root is not None:
            refresh_multi_item_metadata(session.page, root)
    return True


def _bind_secondary(page, extras: dict[str, Any], product: dict[str, Any]) -> None:
    from .operations import _price_parts

    value = product.get("secondary_price")
    if value in (None, ""):
        value = product.get("promotion_price")
    if value in (None, ""):
        value = product.get("retail_price")
    if value not in (None, ""):
        whole, cents = _price_parts(value)
        _set_extra_text(page, extras, "app_price_currency", "R$")
        _set_extra_text(page, extras, "app_price_integer", whole)
        _set_extra_text(page, extras, "app_price_cents", cents)
        _set_extra_text(page, extras, "app_unit", str(product.get("secondary_unit") or product.get("unit") or "UN").upper().lstrip("/"))
    _set_extra_text(page, extras, "promotion", str(product.get("promotion_label") or "PROMOÇÃO"))


def _set_extra_text(page, extras: dict[str, Any], key: str, text: str) -> None:
    raw = extras.get(key)
    ids = raw if isinstance(raw, (list, tuple)) else [raw]
    for node_id in ids:
        node = page.node(str(node_id or ""))
        if node is not None and node.kind is NodeKind.TEXT:
            node.text = text


def product_cells_for_root(page, root_slot_id: str) -> list[SmartSlot]:
    root = page.slots.get(str(root_slot_id))
    if not is_multi_item_root(root):
        return []
    return [
        page.slots[slot_id]
        for slot_id in root.metadata.get("product_cell_slot_ids") or []
        if slot_id in page.slots and is_product_cell(page.slots[slot_id])
    ]


def refresh_multi_item_metadata(page, root_slot: SmartSlot) -> None:
    if not is_multi_item_root(root_slot):
        return
    root = page.node(str(root_slot.metadata.get("root_node_id") or ""))
    if root is not None:
        root_slot.metadata["effective_bounds"] = _rect_dict(root.rect.normalized())
    cells = product_cells_for_root(page, root_slot.id)
    root_slot.metadata["product_cell_count"] = len(cells)
    root_slot.metadata["state"] = "filled" if cells and all(cell.product_id for cell in cells) else ("partial" if any(cell.product_id for cell in cells) else "empty")
    for cell in cells:
        cell_root = page.node(str(cell.metadata.get("root_node_id") or ""))
        if cell_root is not None:
            cell.metadata["effective_bounds"] = _rect_dict(cell_root.rect.normalized())
        refresh_item_slot_metadata(page, cell)


def validate_multi_item_ownership(page, root_slot: SmartSlot) -> dict[str, Any]:
    if not is_multi_item_root(root_slot):
        raise ValueError("SmartSlot não é MultiItemSlotRoot.")
    root_id = str(root_slot.metadata.get("root_node_id") or "")
    root = page.node(root_id)
    if root is None or root.parent_id is not None:
        raise ValueError("MultiItemSlotRoot precisa ser um root visual da página.")
    shared = {str(item) for item in root_slot.metadata.get("shared_visual_nodes") or []}
    seen: set[str] = set()
    cells = product_cells_for_root(page, root_slot.id)
    expected = int(root_slot.metadata.get("product_cell_count") or 0)
    if len(cells) != expected:
        raise ValueError(f"Quantidade de ProductCells inválida: {len(cells)} != {expected}")
    for cell in cells:
        cell_root_id = str(cell.metadata.get("root_node_id") or "")
        cell_root = page.node(cell_root_id)
        if cell_root is None or cell_root.parent_id != root_id:
            raise ValueError("ProductCell fora do MultiItemSlotRoot.")
        owned = {cell_root_id, *page.descendants(cell_root_id)}
        if seen & owned:
            raise ValueError("Node pertence a duas ProductCells.")
        if shared & owned:
            raise ValueError("Visual compartilhado foi colocado dentro de ProductCell.")
        seen.update(owned)
        for node_id in owned:
            node = page.node(node_id)
            if node is None:
                raise ValueError("Child órfão em ProductCell.")
            if node_id != cell_root_id:
                node.metadata.setdefault("multi_item_owner_slot_id", cell.id)
    for node_id in shared:
        node = page.node(node_id)
        if node is None or (node.parent_id != root_id and node_id not in page.descendants(root_id)):
            raise ValueError("Visual compartilhado fora do root.")
    return {"root_count": 1, "product_cell_count": len(cells), "shared_visual_owner": root_slot.id, "cell_nodes_unique": True}


def duplicate_multi_item_slot(
    session: GraphicsSession,
    root_slot_id: str,
    *,
    dx: float = 20.0,
    dy: float = 20.0,
    include_product: bool = False,
) -> SmartSlot:
    source = session.page.slots.get(str(root_slot_id))
    if is_product_cell(source):
        source = session.page.slots.get(str(source.metadata.get("multi_item_root_slot_id") or ""))
    if not is_multi_item_root(source):
        raise KeyError(f"MultiItemSlot inexistente: {root_slot_id}")
    source_node = session.page.node(str(source.metadata.get("root_node_id") or ""))
    if source_node is None:
        raise KeyError("Raiz visual multi-item inexistente.")
    old = source_node.rect.normalized()
    clone = create_multi_item_slot(
        session,
        str(source.metadata.get("preset_id") or ""),
        x=old.x + float(dx),
        y=old.y + float(dy),
    )
    clone_node = session.page.node(str(clone.metadata.get("root_node_id") or ""))
    if clone_node is not None:
        session.resize_node(clone_node.id, x=old.x + float(dx), y=old.y + float(dy), width=old.width, height=old.height)
    if include_product:
        source_cells = product_cells_for_root(session.page, source.id)
        clone_cells = product_cells_for_root(session.page, clone.id)
        for source_cell, clone_cell in zip(source_cells, clone_cells, strict=True):
            snapshot = deepcopy(source_cell.metadata.get("product_snapshot") or {})
            if source_cell.product_id and snapshot:
                product = deepcopy(snapshot)
                product.setdefault("id", source_cell.product_id)
                bind_product_to_multi_item_cell(session, clone_cell.id, product)
    refresh_multi_item_metadata(session.page, clone)
    return clone


def _cell_metadata(root_slot_id: str, cell_slot_id: str, index: int, role: str, *, placeholder: bool = False) -> dict[str, Any]:
    return {
        "manual_item_slot_child": True,
        "multi_item_product_cell_child": True,
        "multi_item_root_slot_id": root_slot_id,
        "multi_item_owner_slot_id": cell_slot_id,
        "product_cell_index": index,
        "item_slot_role_area": role,
        "ownership_kind": "product_cell_role",
        "placeholder": placeholder,
    }


def _cell_layout(family_id: str, index: int) -> dict[str, Any]:
    layout = deepcopy(_CELL_LAYOUTS[family_id])
    profiles = _COMPACT_SOURCE_PROFILES.get(family_id)
    if not profiles:
        return layout
    from .slot_corpus_calibration import profile_parameters

    source = profile_parameters(profiles[index])
    bounds = dict(source.get("roleBounds") or {})
    for role in ("image", "name", "price", "unit"):
        if role in bounds:
            layout[role] = deepcopy(bounds[role])
    layout["secondary_bounds"] = deepcopy(bounds.get("secondaryPrice"))
    layout["promotion_bounds"] = deepcopy(bounds.get("promotion"))
    layout["secondary_components"] = deepcopy(source.get("secondaryComponents") or {})
    layout["image_copy_bounds"] = deepcopy(source.get("imageCopyBounds") or [])
    return layout


def _text_style(size: float, color: str, *, wrap: bool, font_family: str) -> dict[str, Any]:
    return {
        "font_family": font_family,
        "source_font_family": "Anton",
        "font_size": float(size),
        "font_size_unit": "pt",
        "font_weight": 400,
        "color": color,
        "fill": color,
        "align": "center",
        "v_align": "center",
        "fit_inside_box": True,
        "semantic_fit_policy": "overflow_only",
        "nowrap": not wrap,
    }


def _absolute(parent: Rect, relative: list[float]) -> Rect:
    x, y, width, height = (float(item) for item in relative)
    return Rect(parent.x + x * parent.width, parent.y + y * parent.height, max(1.0, width * parent.width), max(1.0, height * parent.height))


def _transform(rect: Rect) -> Transform:
    return Transform(x=rect.x, y=rect.y, width=rect.width, height=rect.height)


def _rect_dict(rect: Rect) -> dict[str, float]:
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}
