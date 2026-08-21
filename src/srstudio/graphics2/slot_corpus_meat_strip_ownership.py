from __future__ import annotations

"""Ownership model for the supervised Quinta3 Meat Strip.

The PPTX ground truth contains one shared row decoration (Group 2 / Freeform 3 /
TextBox 4 + separators) and four product-specific semantic clusters.  Runtime
state therefore uses one persistent ``MeatStripRoot`` containing four mutable
ProductCell roots (the existing manual SmartSlots).  Source/provenance IDs may
be referenced by multiple cells; mutable runtime nodes are never shared between
cells.

SR Scene stores absolute transforms even for grouped nodes.  The parent/child
relationship is authoritative for ownership and generic group MOVE/RESIZE
propagation.  Product content is normalized from source page-space to the cell,
while the cell is normalized from source page-space to the shared strip root.
"""

from copy import deepcopy
from typing import Any

from .model import GraphicsNode, NodeKind, Rect, SmartSlot, Transform
from .slot_corpus_full_card import (
    MEAT_FAMILY_ID,
    MEAT_STRIP_FULL_CARD_PROFILES,
    MEAT_STRIP_SOURCE_PAGE_BACKGROUND,
    MEAT_STRIP_SOURCE_SEPARATOR_IDS,
    MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU,
    MEAT_STRIP_SOURCE_STRIP_FILL,
    MEAT_STRIP_SOURCE_STRIP_GROUP_ID,
    MEAT_STRIP_SOURCE_STRIP_OVERLAY_ID,
    MEAT_STRIP_SOURCE_STRIP_PATH_ID,
    SOURCE_FILE,
    SOURCE_SHA256,
    _strip_segment_path,
    meat_full_card_profile,
)

PROFILE_ORDER = ("costela", "pernil", "musculo", "moela")
_PAGE_ROOTS_KEY = "quinta3_meat_strip_roots"


def _source_strip_bounds() -> Rect:
    roots = [meat_full_card_profile(profile_id)["root_emu"] for profile_id in PROFILE_ORDER]
    left = min(float(root[0]) for root in roots)
    top = min(float(root[1]) for root in roots)
    right = max(float(root[0]) + float(root[2]) for root in roots)
    bottom = max(float(root[1]) + float(root[3]) for root in roots)
    return Rect(left, top, right - left, bottom - top)


_SOURCE_STRIP = _source_strip_bounds()
_SOURCE_STRIP_Y = 9628281.0
_SOURCE_STRIP_HEIGHT = 306437.0
_SOURCE_SEPARATOR_Y = 8736104.0
_SOURCE_SEPARATOR_HEIGHT = 790533.0


def next_meat_profile(page) -> str:
    """Return the first source cell not already represented in the open row."""

    open_root = _find_open_strip_root(page)
    used: set[str] = set()
    if open_root is not None:
        for slot_id in _live_cell_slot_ids(page, open_root):
            slot = page.slots.get(slot_id)
            if slot is not None:
                profile = str(slot.metadata.get("full_card_profile") or slot.metadata.get("supervised_profile") or "")
                if profile:
                    used.add(profile)
    for profile_id in PROFILE_ORDER:
        if profile_id not in used:
            return profile_id
    return PROFILE_ORDER[0]


def normalize_meat_strip_ownership(page, slot: SmartSlot, *, profile_id: str) -> dict[str, Any]:
    """Convert one materialized Meat Strip ItemSlot into a ProductCell.

    ``apply_meat_strip_full_card`` may transiently materialize legacy per-cell
    copies of the shared row decoration.  This function removes those copies,
    creates/reuses exactly one shared root, reparents the cell, and remaps the
    whole product-specific subtree to its source-relative cell position.
    """

    if str(slot.metadata.get("preset_id") or "") != MEAT_FAMILY_ID:
        raise ValueError("Ownership normalization is restricted to quinta3-meat-strip")
    profile_id = _profile_id(profile_id)
    profile = meat_full_card_profile(profile_id)
    cell_root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if cell_root is None:
        raise KeyError("ProductCell root ausente")

    old_cell = cell_root.rect.normalized()
    legacy_visual_ids = _remove_legacy_cell_visuals(page, slot, cell_root.id)

    strip_root = _resolve_strip_root(page, slot, profile, old_cell)
    target_cell = _cell_rect_in_strip(strip_root.rect.normalized(), profile)
    _scale_subtree(page, cell_root.id, old_cell, target_cell)
    _reparent(page, cell_root.id, strip_root.id)

    shared = _ensure_shared_visuals(page, strip_root)
    separator_id = str(profile.get("separator_source_id") or "")
    dependency_ids = [shared["background"], shared["group"], shared["path"], shared["overlay"]]
    if separator_id and separator_id in shared["separators"]:
        dependency_ids.append(shared["separators"][separator_id])

    # Full-card visual IDs are dependencies for fidelity/provenance, not
    # ProductCell-owned decorative nodes.  This distinction prevents one cell
    # from deleting or moving shared nodes when its variant changes.
    slot.metadata["full_card_visual_nodes"] = dependency_ids
    slot.metadata["full_card_visual_owner_root_id"] = strip_root.id
    slot.metadata["decorative_nodes"] = []
    slot.metadata["meat_strip_root_id"] = strip_root.id
    slot.metadata["owner_kind"] = "product_cell"
    slot.metadata["owner_slot_id"] = slot.id
    slot.metadata["full_card_profile"] = profile_id
    slot.metadata["supervised_profile"] = profile_id
    slot.metadata["runtime_node_ids_unique"] = True
    slot.metadata["source_node_ids_shared_by_provenance_only"] = True
    slot.metadata["cell_relative_transform"] = _relative_dict(target_cell, strip_root.rect.normalized())

    # apply_quinta3_variant stores every transient visual in quinta3_variant_nodes.
    # Keep only live ProductCell-owned runtime nodes so a later variant switch
    # cannot delete the shared MeatStripRoot subtree.
    slot.metadata["quinta3_variant_nodes"] = [
        str(node_id)
        for node_id in slot.metadata.get("quinta3_variant_nodes") or []
        if str(node_id) in page.nodes and str(node_id) not in set(dependency_ids)
    ]

    cell_root.metadata["manual_item_slot_root"] = True
    cell_root.metadata["product_cell_root"] = True
    cell_root.metadata["owner_slot_id"] = slot.id
    cell_root.metadata["meat_strip_root_id"] = strip_root.id
    cell_root.metadata["source_profile"] = profile_id
    cell_root.metadata["source_root_emu"] = list(profile["root_emu"])
    cell_root.metadata["cell_relative_transform"] = deepcopy(slot.metadata["cell_relative_transform"])

    _register_cell(page, strip_root, slot, profile_id)
    _prune_variant_node_metadata(page, legacy_visual_ids)
    return ownership_snapshot(page, slot)


def ownership_snapshot(page, slot: SmartSlot) -> dict[str, Any]:
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    strip = page.node(str(slot.metadata.get("meat_strip_root_id") or ""))
    descendant_ids = page.descendants(root.id) if root is not None else []
    runtime_ids = [root.id, *descendant_ids] if root is not None else []
    source_ids = sorted(
        {
            str(node.metadata.get("source_shape_id") or "")
            for node_id in runtime_ids
            if (node := page.node(node_id)) is not None and str(node.metadata.get("source_shape_id") or "")
        }
    )
    return {
        "slot_root_id": root.id if root is not None else "",
        "slot_id": slot.id,
        "product_id": slot.product_id,
        "parent_id": root.parent_id if root is not None else "",
        "strip_root_id": strip.id if strip is not None else "",
        "child_ids": list(root.children) if root is not None else [],
        "descendant_ids": descendant_ids,
        "runtime_node_ids": runtime_ids,
        "source_node_ids": source_ids,
        "role": "product_cell",
        "owner_slot_cell": slot.id,
        "transform": _rect_dict(root.rect.normalized()) if root is not None else {},
        "relative_transform": _relative_dict(root.rect.normalized(), strip.rect.normalized()) if root is not None and strip is not None else {},
    }


def strip_ownership_snapshot(page, strip_root_id: str) -> dict[str, Any]:
    root = page.node(str(strip_root_id or ""))
    if root is None:
        return {}
    return {
        "root_id": root.id,
        "cell_slot_ids": _live_cell_slot_ids(page, root),
        "cell_root_ids": [str(value) for value in dict(root.metadata.get("cell_root_ids") or {}).values()],
        "shared_visual_nodes": list(root.metadata.get("shared_visual_nodes") or []),
        "transform": _rect_dict(root.rect.normalized()),
    }


def _profile_id(value: str) -> str:
    key = str(value or "").strip()
    return key if key in MEAT_STRIP_FULL_CARD_PROFILES else "costela"


def _resolve_strip_root(page, slot: SmartSlot, profile: dict[str, Any], cell_rect: Rect) -> GraphicsNode:
    existing_id = str(slot.metadata.get("meat_strip_root_id") or "")
    existing = page.node(existing_id)
    if existing is not None and existing.metadata.get("meat_strip_root"):
        return existing

    existing = _find_open_strip_root(page)
    if existing is not None:
        return existing

    source = profile["root_emu"]
    scale_x = cell_rect.width / max(float(source[2]), 1e-9)
    scale_y = cell_rect.height / max(float(source[3]), 1e-9)
    strip_rect = Rect(
        cell_rect.x - (float(source[0]) - _SOURCE_STRIP.x) * scale_x,
        cell_rect.y - (float(source[1]) - _SOURCE_STRIP.y) * scale_y,
        _SOURCE_STRIP.width * scale_x,
        _SOURCE_STRIP.height * scale_y,
    )
    root = GraphicsNode(
        kind=NodeKind.GROUP,
        name="MEAT STRIP ROOT · quinta3-meat-strip",
        transform=Transform(x=strip_rect.x, y=strip_rect.y, width=strip_rect.width, height=strip_rect.height),
        z_index=-30,
        metadata={
            "meat_strip_root": True,
            "quinta3_family": MEAT_FAMILY_ID,
            "source_file": SOURCE_FILE,
            "source_sha256": SOURCE_SHA256,
            "source_strip_emu": _rect_dict(_SOURCE_STRIP),
            "cell_slot_ids": [],
            "cell_root_ids": {},
            "profile_by_slot": {},
            "shared_visual_nodes": [],
            "ownership_model": "single-strip-container-with-product-cells",
        },
    )
    page.add_node(root)
    roots = [str(node_id) for node_id in page.metadata.get(_PAGE_ROOTS_KEY) or [] if page.node(str(node_id)) is not None]
    if root.id not in roots:
        roots.append(root.id)
    page.metadata[_PAGE_ROOTS_KEY] = roots
    return root


def _find_open_strip_root(page) -> GraphicsNode | None:
    candidates: list[GraphicsNode] = []
    for root_id in list(page.metadata.get(_PAGE_ROOTS_KEY) or []):
        root = page.node(str(root_id))
        if root is None or not root.metadata.get("meat_strip_root"):
            continue
        if len(_live_cell_slot_ids(page, root)) < len(PROFILE_ORDER):
            candidates.append(root)
    if candidates:
        return candidates[-1]
    # Backward-safe fallback when page metadata was absent but a persisted root
    # itself survived correctly.
    for root in page.nodes.values():
        if root.metadata.get("meat_strip_root") and len(_live_cell_slot_ids(page, root)) < len(PROFILE_ORDER):
            return root
    return None


def _live_cell_slot_ids(page, strip_root: GraphicsNode) -> list[str]:
    out: list[str] = []
    for slot_id in list(strip_root.metadata.get("cell_slot_ids") or []):
        slot = page.slots.get(str(slot_id))
        if slot is None:
            continue
        root = page.node(str(slot.metadata.get("root_node_id") or ""))
        if root is None or root.parent_id != strip_root.id:
            continue
        out.append(str(slot_id))
    strip_root.metadata["cell_slot_ids"] = out
    return out


def _register_cell(page, strip_root: GraphicsNode, slot: SmartSlot, profile_id: str) -> None:
    live = _live_cell_slot_ids(page, strip_root)
    if slot.id not in live:
        live.append(slot.id)
    order = {profile: index for index, profile in enumerate(PROFILE_ORDER)}
    live.sort(key=lambda slot_id: order.get(str(page.slots[slot_id].metadata.get("full_card_profile") or ""), 99))
    strip_root.metadata["cell_slot_ids"] = live
    roots = {
        str(slot_id): str(page.slots[slot_id].metadata.get("root_node_id") or "")
        for slot_id in live
        if slot_id in page.slots
    }
    profiles = {
        str(slot_id): str(page.slots[slot_id].metadata.get("full_card_profile") or "")
        for slot_id in live
        if slot_id in page.slots
    }
    strip_root.metadata["cell_root_ids"] = roots
    strip_root.metadata["profile_by_slot"] = profiles
    strip_root.metadata["cell_count"] = len(live)
    strip_root.metadata["ownership_complete"] = len(live) == len(PROFILE_ORDER)


def _cell_rect_in_strip(strip: Rect, profile: dict[str, Any]) -> Rect:
    source = profile["root_emu"]
    return Rect(
        strip.x + ((float(source[0]) - _SOURCE_STRIP.x) / _SOURCE_STRIP.width) * strip.width,
        strip.y + ((float(source[1]) - _SOURCE_STRIP.y) / _SOURCE_STRIP.height) * strip.height,
        (float(source[2]) / _SOURCE_STRIP.width) * strip.width,
        (float(source[3]) / _SOURCE_STRIP.height) * strip.height,
    )


def _remove_legacy_cell_visuals(page, slot: SmartSlot, cell_root_id: str) -> list[str]:
    candidates = [str(node_id) for node_id in slot.metadata.get("full_card_visual_nodes") or []]
    removed: list[str] = []
    for node_id in candidates:
        node = page.node(node_id)
        if node is None:
            continue
        if node.parent_id != cell_root_id and node_id not in page.descendants(cell_root_id):
            continue
        removed.extend(item.id for item in page.remove_node(node_id, recursive=True))
    return removed


def _ensure_shared_visuals(page, strip_root: GraphicsNode) -> dict[str, Any]:
    raw = strip_root.metadata.get("shared_visual_map")
    if isinstance(raw, dict):
        background = page.node(str(raw.get("background") or ""))
        group = page.node(str(raw.get("group") or ""))
        path = page.node(str(raw.get("path") or ""))
        overlay = page.node(str(raw.get("overlay") or ""))
        separators = dict(raw.get("separators") or {})
        if background and group and path and overlay and all(page.node(str(node_id)) is not None for node_id in separators.values()):
            return {
                "background": background.id,
                "group": group.id,
                "path": path.id,
                "overlay": overlay.id,
                "separators": {str(key): str(value) for key, value in separators.items()},
            }

    root_rect = strip_root.rect.normalized()
    background = GraphicsNode(
        kind=NodeKind.RECT,
        name="MEAT STRIP ROOT · SOURCE BACKGROUND",
        transform=Transform(x=root_rect.x, y=root_rect.y, width=root_rect.width, height=root_rect.height),
        z_index=-20,
        style={"fill": MEAT_STRIP_SOURCE_PAGE_BACKGROUND, "stroke": "transparent", "stroke_width": 0.0},
        metadata={
            "meat_strip_shared_visual": True,
            "owner_root_id": strip_root.id,
            "source_kind": "inherited-slide-background",
            "source_background": MEAT_STRIP_SOURCE_PAGE_BACKGROUND,
            "source_file": SOURCE_FILE,
            "source_sha256": SOURCE_SHA256,
        },
    )
    page.add_node(background, parent_id=strip_root.id)

    strip_rect = Rect(
        root_rect.x,
        root_rect.y + ((_SOURCE_STRIP_Y - _SOURCE_STRIP.y) / _SOURCE_STRIP.height) * root_rect.height,
        root_rect.width,
        (_SOURCE_STRIP_HEIGHT / _SOURCE_STRIP.height) * root_rect.height,
    )
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="MEAT STRIP ROOT · SOURCE GROUP 2",
        transform=Transform(x=strip_rect.x, y=strip_rect.y, width=strip_rect.width, height=strip_rect.height),
        z_index=0,
        metadata={
            "meat_strip_shared_visual": True,
            "owner_root_id": strip_root.id,
            "source_shape_id": str(MEAT_STRIP_SOURCE_STRIP_GROUP_ID),
            "source_name": "Group 2",
            "source_shared_row_decoration": True,
        },
    )
    page.add_node(group, parent_id=strip_root.id)

    path = GraphicsNode(
        kind=NodeKind.PATH,
        name="MEAT STRIP ROOT · Freeform 3",
        transform=Transform(x=strip_rect.x, y=strip_rect.y, width=strip_rect.width, height=strip_rect.height),
        z_index=0,
        style={"fill": MEAT_STRIP_SOURCE_STRIP_FILL, "stroke": "transparent", "stroke_width": 0.0},
        metadata={
            "meat_strip_shared_visual": True,
            "owner_root_id": strip_root.id,
            "source_shape_id": str(MEAT_STRIP_SOURCE_STRIP_PATH_ID),
            "source_name": "Freeform 3",
            "source_geometry": "custGeom",
            "source_shared_row_decoration": True,
            "source_segment": "single",
            "custom_path": _strip_segment_path(_SOURCE_STRIP.width, "single"),
        },
    )
    page.add_node(path, parent_id=group.id)

    overlay_y = strip_rect.y + (19050.0 / 562005.0) * strip_rect.height
    overlay_h = (542955.0 / 562005.0) * strip_rect.height
    overlay = GraphicsNode(
        kind=NodeKind.RECT,
        name="MEAT STRIP ROOT · TextBox 4",
        transform=Transform(x=strip_rect.x, y=overlay_y, width=strip_rect.width, height=overlay_h),
        z_index=1,
        style={"fill": "transparent", "stroke": "transparent", "stroke_width": 0.0},
        metadata={
            "meat_strip_shared_visual": True,
            "owner_root_id": strip_root.id,
            "source_shape_id": str(MEAT_STRIP_SOURCE_STRIP_OVERLAY_ID),
            "source_name": "TextBox 4",
            "source_geometry": "rect",
            "source_empty_textbox": True,
        },
    )
    page.add_node(overlay, parent_id=group.id)

    separators: dict[str, str] = {}
    source_boundaries = (
        ("5", float(MEAT_STRIP_FULL_CARD_PROFILES["costela"]["root_emu"][0]) + float(MEAT_STRIP_FULL_CARD_PROFILES["costela"]["root_emu"][2])),
        ("6", float(MEAT_STRIP_FULL_CARD_PROFILES["pernil"]["root_emu"][0]) + float(MEAT_STRIP_FULL_CARD_PROFILES["pernil"]["root_emu"][2])),
        ("7", float(MEAT_STRIP_FULL_CARD_PROFILES["musculo"]["root_emu"][0]) + float(MEAT_STRIP_FULL_CARD_PROFILES["musculo"]["root_emu"][2])),
    )
    for source_id, source_x in source_boundaries:
        if int(source_id) not in MEAT_STRIP_SOURCE_SEPARATOR_IDS:
            continue
        x = root_rect.x + ((source_x - _SOURCE_STRIP.x) / _SOURCE_STRIP.width) * root_rect.width
        y = root_rect.y + ((_SOURCE_SEPARATOR_Y - _SOURCE_STRIP.y) / _SOURCE_STRIP.height) * root_rect.height
        h = (_SOURCE_SEPARATOR_HEIGHT / _SOURCE_STRIP.height) * root_rect.height
        stroke = (MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU / _SOURCE_STRIP.width) * root_rect.width
        node = GraphicsNode(
            kind=NodeKind.LINE,
            name=f"MEAT STRIP ROOT · AutoShape {source_id}",
            transform=Transform(x=x, y=y, width=0.0, height=h),
            z_index=2,
            style={
                "stroke": MEAT_STRIP_SOURCE_STRIP_FILL,
                "outline": MEAT_STRIP_SOURCE_STRIP_FILL,
                "stroke_width": stroke,
                "line_width": stroke,
            },
            metadata={
                "meat_strip_shared_visual": True,
                "owner_root_id": strip_root.id,
                "source_shape_id": source_id,
                "source_name": f"AutoShape {source_id}",
                "source_geometry": "line",
                "source_flip_v": True,
                "source_line_width_emu": MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU,
            },
        )
        page.add_node(node, parent_id=strip_root.id)
        separators[source_id] = node.id

    visual_nodes = [background.id, group.id, path.id, overlay.id, *separators.values()]
    shared_map = {
        "background": background.id,
        "group": group.id,
        "path": path.id,
        "overlay": overlay.id,
        "separators": separators,
    }
    strip_root.metadata["shared_visual_nodes"] = visual_nodes
    strip_root.metadata["shared_visual_map"] = deepcopy(shared_map)
    return shared_map


def _scale_subtree(page, root_id: str, old: Rect, new: Rect) -> None:
    old = old.normalized()
    new = new.normalized()
    ids = [root_id, *page.descendants(root_id)]
    for node_id in ids:
        node = page.node(node_id)
        if node is None:
            continue
        rect = node.rect.normalized()
        rel_x = (rect.x - old.x) / max(old.width, 1e-9)
        rel_y = (rect.y - old.y) / max(old.height, 1e-9)
        rel_w = rect.width / max(old.width, 1e-9)
        rel_h = rect.height / max(old.height, 1e-9)
        node.transform.x = new.x + rel_x * new.width
        node.transform.y = new.y + rel_y * new.height
        node.transform.width = max(1e-6, rel_w * new.width)
        node.transform.height = max(1e-6, rel_h * new.height)


def _reparent(page, node_id: str, parent_id: str) -> None:
    node = page.node(node_id)
    parent = page.node(parent_id)
    if node is None or parent is None:
        raise KeyError("Reparent Meat Strip recebeu runtime node ausente")
    if node.parent_id == parent_id:
        return
    if node.parent_id and page.node(node.parent_id) is not None:
        old_parent = page.node(node.parent_id)
        old_parent.children = [child_id for child_id in old_parent.children if child_id != node_id]
    else:
        page.roots = [root_id for root_id in page.roots if root_id != node_id]
    node.parent_id = parent_id
    if node_id not in parent.children:
        parent.children.append(node_id)


def _prune_variant_node_metadata(page, removed_ids: list[str]) -> None:
    removed = set(removed_ids)
    for other in page.slots.values():
        other.metadata["quinta3_variant_nodes"] = [
            str(node_id)
            for node_id in other.metadata.get("quinta3_variant_nodes") or []
            if str(node_id) not in removed and page.node(str(node_id)) is not None
        ]


def _rect_dict(rect: Rect) -> dict[str, float]:
    return {"x": float(rect.x), "y": float(rect.y), "width": float(rect.width), "height": float(rect.height)}


def _relative_dict(child: Rect, parent: Rect) -> dict[str, float]:
    return {
        "x": (child.x - parent.x) / max(parent.width, 1e-9),
        "y": (child.y - parent.y) / max(parent.height, 1e-9),
        "width": child.width / max(parent.width, 1e-9),
        "height": child.height / max(parent.height, 1e-9),
    }
