from __future__ import annotations

"""Full-card source contracts for the certified Quinta3 meat-strip family.

The PPTX is the visual ground truth.  Unlike the older role-only calibration,
this module freezes the complete visual dependencies of the recurring meat row:
slide background context, the shared burgundy custGeom strip, separator lines,
picture-fill geometry and the exact text-node transforms/styles/z-order.

Only ``quinta3-meat-strip`` is materialized here.  The other four certified
families remain untouched until this family passes the new visual/manual gate.
"""

from copy import deepcopy
from typing import Any

from .model import BindingRole, GraphicsNode, NodeKind, Rect, Transform

SOURCE_FILE = "OFERTAS QUINTA FILÉ NOVO (3).pptx"
SOURCE_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
MEAT_FAMILY_ID = "quinta3-meat-strip"

# Exact source cluster: Group 2 + children 3/4 + separator shapes 5/6/7 plus
# 24 exclusive semantic nodes (6 per product).  The black slide background is
# a visual dependency, but is not a DrawingML node and therefore is tracked
# separately instead of inflating the source-node count.
MEAT_STRIP_SOURCE_CLUSTER_NODE_COUNT = 30
MEAT_STRIP_SOURCE_VISUAL_STRUCTURAL_IDS = (2, 3, 4, 5, 6, 7)
MEAT_STRIP_SOURCE_SEMANTIC_NODE_COUNT = 24
MEAT_STRIP_SOURCE_PAGE_BACKGROUND = "#000000"
MEAT_STRIP_SOURCE_STRIP_FILL = "#470000"
MEAT_STRIP_SOURCE_STRIP_GROUP_ID = 2
MEAT_STRIP_SOURCE_STRIP_PATH_ID = 3
MEAT_STRIP_SOURCE_STRIP_OVERLAY_ID = 4
MEAT_STRIP_SOURCE_SEPARATOR_IDS = (5, 6, 7)
MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU = 19050

# Source shared strip geometry after Group 2 transform, in slide EMUs.
_STRIP_Y = 9628281
_STRIP_HEIGHT = 306437
_STRIP_LEFT = 185365
_STRIP_RIGHT = 5706903
# The curved edge control points are the original custGeom points transformed
# through Group 2.  Keeping them in source units avoids replacing the Canva
# freeform with a generic rounded rectangle.
_CURVE_X_OUTER = 110796.2239619722
_CURVE_X_CONTROL = 49605.30153132078
_CURVE_Y_1 = 68598.20203201039
_CURVE_Y_MID = 153218.2273716426
_CURVE_Y_2 = 237838.7979679896


def _text_style(size: float, spacing_pt: float) -> dict[str, Any]:
    return {
        "font_family": "Anton",
        "source_font_family": "Anton",
        "font_size": float(size),
        "font_size_unit": "pt",
        "font_weight": 400,
        "color": "#FFFFFF",
        "fill": "#FFFFFF",  # backward-compatible metadata; renderer/QML use color.
        "align": "center",
        "v_align": "top",
        "fit_inside_box": False,
        "nowrap": True,
        "letter_spacing_pt": float(spacing_pt),
        "letter_spacing": float(spacing_pt) * (96.0 / 72.0),
        "pptx_auto_fit": "shape",
        "text_insets": {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
    }


MEAT_STRIP_FULL_CARD_PROFILES: dict[str, dict[str, Any]] = {
    "costela": {
        "product": "COSTELA GAÚCHA",
        "root_emu": [185365, 8667562, 1524086, 1267156],
        "stripPosition": "first",
        "separator_source_id": 5,
        "image_asset": {"source_shape_id": 25, "internal_media": "/ppt/media/image3.png", "sha256": "9458fe6054535e4411834407c9af9af24f35d2946f8f027f26f416023a441e3d", "fill_rect": {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}},
        "roles": {
            "image": {"source_id": 25, "z": 11, "relative": [0.295438053, 0.117539593, 0.650744118, 0.782689740]},
            "name": {"source_id": 49, "z": 35, "relative": [0.331380906, 0.0, 0.616225069, 0.175183640], "style": _text_style(7.73, -0.22)},
            "currency": {"source_id": 45, "z": 31, "relative": [0.440067686, 0.850291519, 0.067714683, 0.094915701], "style": _text_style(9.22, -0.26)},
            "integer": {"source_id": 47, "z": 33, "relative": [0.507783025, 0.788655856, 0.184698239, 0.233183602], "style": _text_style(22.08, -0.64)},
            "decimal": {"source_id": 48, "z": 34, "relative": [0.698543914, 0.785306624, 0.074621117, 0.093048528], "style": _text_style(7.80, -0.22)},
            "unit": {"source_id": 46, "z": 32, "relative": [0.712602832, 0.907746165, 0.060562855, 0.082439731], "style": _text_style(7.54, -0.21)},
        },
    },
    "pernil": {
        "product": "PERNIL SUINO S/ OSSO",
        "root_emu": [1709451, 8665852, 1335090, 1268866],
        "stripPosition": "middle",
        "separator_source_id": 6,
        "image_asset": {"source_shape_id": 29, "internal_media": "/ppt/media/image5.png", "sha256": "2dbde9ce6a7cae99bee9d25647af23b3134b1ad680fdbd558946cb05edfcae0e", "fill_rect": {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}},
        "roles": {
            "image": {"source_id": 29, "z": 15, "relative": [0.079233610, 0.089638307, 0.813200608, 0.855642755]},
            "name": {"source_id": 38, "z": 24, "relative": [0.160270094, 0.0, 0.651128388, 0.174912087], "style": _text_style(7.81, -0.22)},
            "currency": {"source_id": 33, "z": 19, "relative": [0.315510565, 0.850493275, 0.077300407, 0.094787787], "style": _text_style(9.22, -0.26)},
            "integer": {"source_id": 36, "z": 22, "relative": [0.401379682, 0.788940676, 0.200628422, 0.232869349], "style": _text_style(22.08, -0.64)},
            "decimal": {"source_id": 37, "z": 23, "relative": [0.624756383, 0.785595957, 0.085184519, 0.092909732], "style": _text_style(7.80, -0.22)},
            "unit": {"source_id": 35, "z": 21, "relative": [0.626625920, 0.907870492, 0.069136163, 0.082316021], "style": _text_style(7.54, -0.21)},
        },
    },
    "musculo": {
        "product": "MÚSCULO BOVINO",
        "root_emu": [3044541, 8680533, 1335232, 1254185],
        "stripPosition": "middle",
        "separator_source_id": 7,
        "image_asset": {"source_shape_id": 28, "internal_media": "/ppt/media/image4.png", "sha256": "3a747c31bfe3aa8ae2326ec91f523f59c400aab069f3d3e94512c500b3a1fad3", "fill_rect": {"l": 0.0, "t": -0.10057, "r": 0.0, "b": -0.40571}},
        "roles": {
            "image": {"source_id": 28, "z": 14, "relative": [0.060553522, 0.250482186, 0.909394023, 0.563687175]},
            "name": {"source_id": 41, "z": 27, "relative": [0.187478281, 0.0, 0.658066913, 0.101789608], "style": _text_style(8.45, -0.24)},
            "currency": {"source_id": 39, "z": 25, "relative": [0.305935598, 0.848743208, 0.077292186, 0.095897336], "style": _text_style(9.22, -0.26)},
            "integer": {"source_id": 26, "z": 12, "relative": [0.383227784, 0.786470098, 0.213811532, 0.235632702], "style": _text_style(22.08, -0.64)},
            "decimal": {"source_id": 27, "z": 13, "relative": [0.601351675, 0.783086227, 0.084414544, 0.094010852], "style": _text_style(7.80, -0.22)},
            "unit": {"source_id": 40, "z": 26, "relative": [0.617017867, 0.906792060, 0.069128811, 0.083292337], "style": _text_style(7.54, -0.21)},
        },
    },
    "moela": {
        "product": "MOELA DE FRANGO",
        "root_emu": [4379773, 8667562, 1327130, 1267156],
        "stripPosition": "last",
        "separator_source_id": None,
        "image_asset": {"source_shape_id": 30, "internal_media": "/ppt/media/image6.png", "sha256": "b2b40eb4f871b131d4c21d7ae40d7a9d0c4232c740ef8fa396b01f1948c35524", "fill_rect": {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}},
        "roles": {
            "image": {"source_id": 30, "z": 16, "relative": [0.012184940, 0.316167070, 0.797549600, 0.555473044]},
            "name": {"source_id": 44, "z": 30, "relative": [0.114410796, 0.0, 0.684153022, 0.191302413], "style": _text_style(8.45, -0.24)},
            "currency": {"source_id": 42, "z": 28, "relative": [0.265995795, 0.850291519, 0.077764047, 0.094915701], "style": _text_style(9.22, -0.26)},
            "integer": {"source_id": 31, "z": 17, "relative": [0.350722235, 0.788655856, 0.212108836, 0.233183602], "style": _text_style(22.08, -0.64)},
            "decimal": {"source_id": 43, "z": 29, "relative": [0.562831825, 0.785306624, 0.085695448, 0.093035112], "style": _text_style(7.80, -0.22)},
            "unit": {"source_id": 34, "z": 20, "relative": [0.578977191, 0.907746165, 0.069550835, 0.082439731], "style": _text_style(7.54, -0.21)},
        },
    },
}


_ROLE_BINDINGS = {
    "image": BindingRole.IMAGE,
    "name": BindingRole.NAME,
    "currency": BindingRole.CURRENCY,
    "integer": BindingRole.PRICE_REAIS,
    "decimal": BindingRole.PRICE_CENTS,
    "unit": BindingRole.UNIT,
}


def meat_full_card_profile(profile_id: str) -> dict[str, Any]:
    key = str(profile_id or "costela").strip() or "costela"
    if key not in MEAT_STRIP_FULL_CARD_PROFILES:
        key = "costela"
    return deepcopy(MEAT_STRIP_FULL_CARD_PROFILES[key])


def apply_meat_strip_full_card(page, slot, *, profile_id: str, requested_position: str = "") -> tuple[Rect, list[str]]:
    """Replace synthetic role-only visuals with the supervised full-card subtree.

    The generic ItemSlot root/bindings stay intact.  We only remove synthetic
    visual backplates that did not exist in the PPTX, then materialize the
    source-derived visual dependencies and exact semantic-node presentation.
    """

    profile = meat_full_card_profile(profile_id)
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        raise KeyError("Raiz do Meat Strip não encontrada.")

    source_root = profile["root_emu"]
    source_ratio = float(source_root[3]) / max(float(source_root[2]), 1.0)
    root.transform.height = max(1.0, float(root.transform.width) * source_ratio)
    root_rect = root.rect.normalized()

    _remove_synthetic_visuals(page, slot)
    _reparent_price_components(page, slot, root.id)

    created: list[str] = []
    context = GraphicsNode(
        kind=NodeKind.RECT,
        name="MEAT FULL CARD · SOURCE BACKGROUND",
        transform=Transform(x=root_rect.x, y=root_rect.y, width=root_rect.width, height=root_rect.height),
        z_index=-20,
        style={"fill": MEAT_STRIP_SOURCE_PAGE_BACKGROUND, "stroke": "transparent", "stroke_width": 0.0},
        metadata={
            "manual_item_slot_child": True,
            "quinta3_variant_node": True,
            "full_card_visual_node": True,
            "source_kind": "inherited-slide-background",
            "source_background": MEAT_STRIP_SOURCE_PAGE_BACKGROUND,
            "source_file": SOURCE_FILE,
            "source_sha256": SOURCE_SHA256,
        },
    )
    page.add_node(context, parent_id=root.id)
    created.append(context.id)

    strip_rect = Rect(
        root_rect.x,
        root_rect.y + ((_STRIP_Y - float(source_root[1])) / float(source_root[3])) * root_rect.height,
        root_rect.width,
        (_STRIP_HEIGHT / float(source_root[3])) * root_rect.height,
    )
    decoration_group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="MEAT FULL CARD · SOURCE GROUP 2",
        transform=Transform(x=strip_rect.x, y=strip_rect.y, width=strip_rect.width, height=strip_rect.height),
        z_index=0,
        metadata={
            "manual_item_slot_child": True,
            "quinta3_variant_node": True,
            "full_card_visual_node": True,
            "source_shape_id": str(MEAT_STRIP_SOURCE_STRIP_GROUP_ID),
            "source_name": "Group 2",
            "source_shared_row_decoration": True,
        },
    )
    page.add_node(decoration_group, parent_id=root.id)
    created.append(decoration_group.id)

    position = str(requested_position or profile.get("stripPosition") or "single").strip().lower()
    if position not in {"single", "first", "middle", "last"}:
        position = str(profile.get("stripPosition") or "single")
    strip_path = GraphicsNode(
        kind=NodeKind.PATH,
        name="MEAT FULL CARD · Freeform 3",
        transform=Transform(x=strip_rect.x, y=strip_rect.y, width=strip_rect.width, height=strip_rect.height),
        z_index=0,
        style={"fill": MEAT_STRIP_SOURCE_STRIP_FILL, "stroke": "transparent", "stroke_width": 0.0},
        metadata={
            "manual_item_slot_child": True,
            "quinta3_variant_node": True,
            "full_card_visual_node": True,
            "source_shape_id": str(MEAT_STRIP_SOURCE_STRIP_PATH_ID),
            "source_name": "Freeform 3",
            "source_geometry": "custGeom",
            "source_shared_row_decoration": True,
            "source_segment": position,
            "custom_path": _strip_segment_path(float(source_root[2]), position),
        },
    )
    page.add_node(strip_path, parent_id=decoration_group.id)
    created.append(strip_path.id)

    # TextBox 4 is structurally part of the source Group 2 subtree but has no
    # fill/stroke/text.  Preserve it as an explicit transparent node instead of
    # silently dropping the PPTX child.
    overlay_y = strip_rect.y + (19050.0 / 562005.0) * strip_rect.height
    overlay_h = (542955.0 / 562005.0) * strip_rect.height
    overlay = GraphicsNode(
        kind=NodeKind.RECT,
        name="MEAT FULL CARD · TextBox 4",
        transform=Transform(x=strip_rect.x, y=overlay_y, width=strip_rect.width, height=overlay_h),
        z_index=1,
        style={"fill": "transparent", "stroke": "transparent", "stroke_width": 0.0},
        metadata={
            "manual_item_slot_child": True,
            "quinta3_variant_node": True,
            "full_card_visual_node": True,
            "source_shape_id": str(MEAT_STRIP_SOURCE_STRIP_OVERLAY_ID),
            "source_name": "TextBox 4",
            "source_geometry": "rect",
            "source_empty_textbox": True,
        },
    )
    page.add_node(overlay, parent_id=decoration_group.id)
    created.append(overlay.id)

    separator_source_id = profile.get("separator_source_id")
    if position in {"first", "middle"} and separator_source_id:
        sep_y = root_rect.y + ((8736104.0 - float(source_root[1])) / float(source_root[3])) * root_rect.height
        sep_h = (790533.0 / float(source_root[3])) * root_rect.height
        stroke = (MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU / float(source_root[2])) * root_rect.width
        separator = GraphicsNode(
            kind=NodeKind.LINE,
            name=f"MEAT FULL CARD · AutoShape {separator_source_id}",
            transform=Transform(x=root_rect.right, y=sep_y, width=0.0, height=sep_h),
            z_index=2,
            style={"stroke": MEAT_STRIP_SOURCE_STRIP_FILL, "outline": MEAT_STRIP_SOURCE_STRIP_FILL, "stroke_width": stroke, "line_width": stroke},
            metadata={
                "manual_item_slot_child": True,
                "quinta3_variant_node": True,
                "full_card_visual_node": True,
                "source_shape_id": str(separator_source_id),
                "source_name": f"AutoShape {separator_source_id}",
                "source_geometry": "line",
                "source_flip_v": True,
                "source_line_width_emu": MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU,
            },
        )
        page.add_node(separator, parent_id=root.id)
        created.append(separator.id)

    _apply_exact_role_nodes(page, slot, root_rect, profile)

    slot.metadata["full_card_visual"] = True
    slot.metadata["full_card_source_file"] = SOURCE_FILE
    slot.metadata["full_card_source_sha256"] = SOURCE_SHA256
    slot.metadata["full_card_source_cluster_node_count"] = MEAT_STRIP_SOURCE_CLUSTER_NODE_COUNT
    slot.metadata["full_card_source_visual_structural_ids"] = list(MEAT_STRIP_SOURCE_VISUAL_STRUCTURAL_IDS)
    slot.metadata["full_card_context_background"] = MEAT_STRIP_SOURCE_PAGE_BACKGROUND
    slot.metadata["full_card_profile"] = str(profile_id or "costela")
    slot.metadata["full_card_strip_position"] = position
    slot.metadata["full_card_visual_nodes"] = list(created)
    slot.metadata["decorative_nodes"] = list(created)
    root.metadata["full_card_visual"] = True
    root.metadata["full_card_profile"] = str(profile_id or "costela")
    root.metadata["full_card_source_sha256"] = SOURCE_SHA256
    return root_rect, created


def _remove_synthetic_visuals(page, slot) -> None:
    for node_id in list(slot.metadata.get("decorative_nodes") or []):
        node = page.node(str(node_id))
        if node is None:
            continue
        if node.metadata.get("item_slot_image_backplate") or node.metadata.get("item_slot_price_background"):
            page.remove_node(node.id)
    slot.metadata["decorative_nodes"] = [
        str(node_id)
        for node_id in slot.metadata.get("decorative_nodes") or []
        if page.node(str(node_id)) is not None
    ]


def _reparent_price_components(page, slot, root_id: str) -> None:
    areas = slot.metadata.setdefault("role_area_nodes", {})
    price_group = page.node(str(areas.get("price") or ""))
    if price_group is None:
        return
    # Keep the semantic PRICEBLOCK root because it is useful to editing/binding,
    # but make it non-visual and ensure no synthetic background survives.
    for child_id in list(price_group.children):
        child = page.node(child_id)
        if child is not None and child.metadata.get("item_slot_price_background"):
            page.remove_node(child.id)
    price_group.style = {}
    price_group.metadata["full_card_semantic_container"] = True
    price_group.metadata["source_visual_node"] = False


def _apply_exact_role_nodes(page, slot, root: Rect, profile: dict[str, Any]) -> None:
    role_specs = profile["roles"]
    for key, binding in _ROLE_BINDINGS.items():
        node = page.node(str(slot.node_by_role.get(binding.value) or ""))
        spec = role_specs[key]
        if node is None:
            continue
        _set_rect(node, _absolute(root, spec["relative"]))
        node.z_index = int(spec["z"])
        node.metadata["source_shape_id"] = str(spec["source_id"])
        node.metadata["source_file"] = SOURCE_FILE
        node.metadata["source_sha256"] = SOURCE_SHA256
        node.metadata["full_card_source_node"] = True
        node.metadata["source_z_index"] = int(spec["z"])
        node.opacity = 1.0
        node.transform.rotation = 0.0
        if key == "image":
            image = profile["image_asset"]
            node.style = {
                "fit": "fill",
                "crop": {},
                "fill_rect": deepcopy(image["fill_rect"]),
                "flip_x": False,
                "flip_y": False,
                "zoom": 1.0,
                "focus_x": 0.5,
                "focus_y": 0.5,
            }
            node.metadata["source_name"] = f"Freeform {spec['source_id']}"
            node.metadata["source_geometry"] = "custGeom-axis-aligned-rect"
            node.metadata["picture_fill"] = True
            node.metadata["pptx_internal_media"] = image["internal_media"]
            node.metadata["image_sha256"] = image["sha256"]
            node.metadata["pptx_fill_rect"] = {"source_kind": "shape", "rect": deepcopy(image["fill_rect"]), "has_outset": any(float(v) < 0.0 for v in image["fill_rect"].values())}
        else:
            node.style = deepcopy(spec["style"])
            node.metadata["source_name"] = f"TextBox {spec['source_id']}"
            node.metadata["source_geometry"] = "rect"
            node.metadata["pptx_vertical_anchor"] = "t"
            node.metadata["pptx_paragraph_alignment"] = "ctr"

    # The semantic price container follows the exact union of its three source
    # children; the UNIT remains an independent source node as in the PPTX.
    areas = slot.metadata.setdefault("role_area_nodes", {})
    price_group = page.node(str(areas.get("price") or ""))
    if price_group is not None:
        ids = [
            slot.node_by_role.get(BindingRole.CURRENCY.value),
            slot.node_by_role.get(BindingRole.PRICE_REAIS.value),
            slot.node_by_role.get(BindingRole.PRICE_CENTS.value),
        ]
        rects = [page.node(str(node_id)).rect.normalized() for node_id in ids if page.node(str(node_id)) is not None]
        if rects:
            union = rects[0]
            for rect in rects[1:]:
                union = union.union(rect)
            _set_rect(price_group, union)
            price_group.z_index = min(int(role_specs[key]["z"]) for key in ("currency", "integer", "decimal"))


def _strip_segment_path(width: float, position: str) -> dict[str, Any]:
    width = max(1.0, float(width))
    height = float(_STRIP_HEIGHT)
    left_curve = position in {"single", "first"}
    right_curve = position in {"single", "last"}
    commands: list[dict[str, Any]] = []

    start_x = width - _CURVE_X_OUTER if right_curve else width
    commands.append({"op": "M", "points": [[start_x, 0.0]]})
    if right_curve:
        commands.append({"op": "C", "points": [[width - _CURVE_X_CONTROL, 0.0], [width, _CURVE_Y_1], [width, _CURVE_Y_MID]]})
        commands.append({"op": "C", "points": [[width, _CURVE_Y_2], [width - _CURVE_X_CONTROL, height], [width - _CURVE_X_OUTER, height]]})
    else:
        commands.append({"op": "L", "points": [[width, 0.0]]})
        commands.append({"op": "L", "points": [[width, height]]})

    if left_curve:
        commands.append({"op": "L", "points": [[_CURVE_X_OUTER, height]]})
        commands.append({"op": "C", "points": [[_CURVE_X_CONTROL, height], [0.0, _CURVE_Y_2], [0.0, _CURVE_Y_MID]]})
        commands.append({"op": "C", "points": [[0.0, _CURVE_Y_1], [_CURVE_X_CONTROL, 0.0], [_CURVE_X_OUTER, 0.0]]})
    else:
        commands.append({"op": "L", "points": [[0.0, height]]})
        commands.append({"op": "L", "points": [[0.0, 0.0]]})
    commands.append({"op": "Z"})
    return {"width": width, "height": height, "paths": [{"width": width, "height": height, "fill_mode": "norm", "stroke": False, "commands": commands}]}


def _absolute(parent: Rect, relative: Any) -> Rect:
    x, y, width, height = (float(value) for value in relative)
    return Rect(
        parent.x + x * parent.width,
        parent.y + y * parent.height,
        max(1.0, width * parent.width),
        max(1.0, height * parent.height),
    )


def _set_rect(node: GraphicsNode, rect: Rect) -> None:
    node.transform.x = float(rect.x)
    node.transform.y = float(rect.y)
    node.transform.width = max(1.0, float(rect.width))
    node.transform.height = max(1.0, float(rect.height))
