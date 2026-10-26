"""Idempotent on-open repair for Beta44 PPT reference slots.

Preserves node IDs, product bindings, manual bounding rectangle, and page IDs.
Only known built-in Beta44 shapes are migrated; custom/user templates are left
untouched. All source measurements are normalized from the supplied PPTX files.
"""
from __future__ import annotations

import copy

from .model import BindingRole, GraphicsNode, NodeKind, Rect, Transform

BLUE = "#105594"
WHITE = "#FFFFFF"


def _rect(parent: Rect, bounds) -> Rect:
    x, y, w, h = map(float, bounds)
    return Rect(parent.x + x * parent.width, parent.y + y * parent.height,
                w * parent.width, h * parent.height)


def _set_bounds(node, rect: Rect, style=None):
    if node is None:
        return
    node.transform.x = rect.x
    node.transform.y = rect.y
    node.transform.width = max(.1, rect.width)
    node.transform.height = max(.1, rect.height)
    if style is not None:
        node.style = copy.deepcopy(style)


def migrate_reference_slot(page, slot, presets) -> bool:
    preset_id = str(slot.metadata.get("preset_id") or "")
    if preset_id not in ("individual-beta44", "multi-cell-beta44"):
        return False
    if int(slot.metadata.get("reference_fidelity_revision") or 0) >= 47:
        return False
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return False
    root_rect = root.rect.normalized()
    roles = presets[preset_id].roles

    # The PPTX Individual has two cutouts. Repair existing Beta46 scenes
    # without modifying product IDs or the source image asset.
    if preset_id == "individual-beta44":
        primary = page.node(str(slot.node_by_role.get(BindingRole.IMAGE.value) or ""))
        repeated = page.node(str(slot.metadata.get("image_repeat_node_id") or ""))
        if primary is not None:
            repeat_rect = _rect(root_rect, [.236, .005, .41, .985])
            if repeated is None:
                repeated = GraphicsNode(
                    kind=NodeKind.IMAGE,
                    name="IMAGE ROLE · repeated product",
                    transform=Transform(x=repeat_rect.x, y=repeat_rect.y,
                                        width=repeat_rect.width, height=repeat_rect.height),
                    style=copy.deepcopy(primary.style),
                    z_index=9,
                    metadata={"manual_item_slot_child": True,
                              "item_slot_repeated_image": True,
                              "placeholder": primary.metadata.get("placeholder", True)},
                )
                page.add_node(repeated, parent_id=root.id)
                slot.metadata["image_repeat_node_id"] = repeated.id
            else:
                _set_bounds(repeated, repeat_rect, roles["image"].get("style"))
            repeated.asset_id = primary.asset_id
            repeated.metadata.pop("bound_image_source", None)
            if primary.metadata.get("bound_image_source"):
                repeated.metadata["bound_image_source"] = primary.metadata["bound_image_source"]
            repeated.visible = primary.visible

    for role, key in ((BindingRole.IMAGE, "image"),
                      (BindingRole.NAME, "name"),
                      (BindingRole.UNIT, "unit"),
                      (BindingRole.RETAIL_PRICE, "secondary_price"),
                      (BindingRole.LIMIT, "limit")):
        if key in roles:
            node = page.node(str(slot.node_by_role.get(role.value) or ""))
            if node is not None:
                spec = roles[key]
                _set_bounds(node, _rect(root_rect, spec["bounds"]), spec.get("style"))

    price = page.node(str(slot.metadata.get("role_area_nodes", {}).get("price") or ""))
    price_spec = roles["price"]
    price_rect = _rect(root_rect, price_spec["bounds"])
    _set_bounds(price, price_rect)
    for role, key in ((BindingRole.CURRENCY, "currency"),
                      (BindingRole.PRICE_REAIS, "integer"),
                      (BindingRole.PRICE_CENTS, "decimal")):
        node = page.node(str(slot.node_by_role.get(role.value) or ""))
        spec = roles[key]
        _set_bounds(node, _rect(price_rect, spec["bounds"]), spec["style"])

    for nid in slot.metadata.get("decorative_nodes") or []:
        node = page.node(str(nid))
        if node is None:
            continue
        if node.metadata.get("item_slot_image_backplate"):
            node.visible = False
        elif node.metadata.get("item_slot_background"):
            if preset_id == "individual-beta44":
                _set_bounds(node, root_rect, presets[preset_id].background)
            else:
                node.visible = False
        elif node.metadata.get("item_slot_price_background"):
            if preset_id == "individual-beta44":
                _set_bounds(node, price_rect, price_spec["background"])
            else:
                node.visible = False

    club = page.node(str(slot.metadata.get("club_label_node_id") or ""))
    if club is not None and "club_label" in roles:
        spec = roles["club_label"]
        _set_bounds(club, _rect(root_rect, spec["bounds"]), spec["style"])

    promotional = page.node(str(slot.metadata.get("promotion_label_node_id") or ""))
    if promotional is None:
        from .item_slots import _make_text
        spec = roles["promotion_label"]
        promotional = _make_text(
            page, root.id, "PROMOTION LABEL",
            "PROMOÇÃO" if preset_id == "individual-beta44" else "NA PROMOÇÃO",
            _rect(root_rect, spec["bounds"]),
            spec["style"],
        )
        promotional.metadata["item_slot_role_area"] = "promotion_label"
        slot.metadata["promotion_label_node_id"] = promotional.id
    else:
        spec = roles["promotion_label"]
        _set_bounds(promotional, _rect(root_rect, spec["bounds"]), spec["style"])
    promotional.visible = slot.metadata.get("price_variant") != "two"

    for nid in page.descendants(root.id):
        node = page.node(nid)
        if node is None:
            continue
        if node.metadata.get("item_slot_background"):
            node.z_index = -70
        elif node.metadata.get("item_slot_image_backplate"):
            node.z_index = -40
        elif node.metadata.get("item_slot_price_background"):
            node.z_index = 30
        elif node.metadata.get("item_slot_repeated_image"):
            node.z_index = 9
        elif node.kind is NodeKind.IMAGE:
            node.z_index = 10
        elif node.kind is NodeKind.TEXT:
            node.z_index = 20 if node.binding_role == BindingRole.NAME else 50

    # Reflow old Beta44 product names without changing the saved SKU or
    # user-specified manual paragraph breaks.
    name_node = page.node(str(slot.node_by_role.get(BindingRole.NAME.value) or ""))
    if name_node is not None and name_node.text and "\n" not in name_node.text:
        from .item_slots import _format_reference_name
        name_node.text = _format_reference_name(
            name_node.text, max_chars=19 if preset_id == "multi-cell-beta44" else 18)

    root.metadata["reference_fidelity_revision"] = 47
    slot.metadata["reference_fidelity_revision"] = 47
    return True


def migrate_multi_parent(page, parent_id: str) -> bool:
    """Restore the original continuous ribbon even on already-saved Beta44."""
    root = page.node(parent_id)
    if root is None or not root.metadata.get("multi_slot_beta44"):
        return False
    if int(root.metadata.get("reference_fidelity_revision") or 0) >= 47:
        return False
    rect = root.rect.normalized()
    count = int(root.metadata.get("multi_count") or 5)
    footer = None
    separators = []
    paper = None
    for node_id in root.children:
        node = page.node(node_id)
        if node is None:
            continue
        if node.name == "Faixa azul contínua":
            footer = node
        elif node.name == "Fundo branco da faixa":
            paper = node
        elif node.name.startswith("Divisor "):
            separators.append(node)

    if paper is None:
        paper = GraphicsNode(
            kind=NodeKind.RECT, name="Fundo branco da faixa",
            transform=Transform(x=rect.x, y=rect.y, width=rect.width,
                                height=rect.height * .748),
            z_index=-110,
            style={"fill": WHITE, "stroke_width": 0},
            metadata={"multi_item_decoration": True})
        page.add_node(paper, parent_id=root.id)
    else:
        _set_bounds(paper, Rect(rect.x, rect.y, rect.width, rect.height * .748))
        paper.z_index = -110
        paper.style = {"fill": WHITE, "stroke_width": 0}
    if footer is not None:
        _set_bounds(footer, Rect(rect.x, rect.y + rect.height * .748,
                                 rect.width, rect.height * .252))
        footer.style = {"fill": BLUE, "stroke_width": 0, "radius_ratio": .29}
        footer.z_index = -100
    for index, sep in enumerate(sorted(separators, key=lambda n: n.name), start=1):
        _set_bounds(sep, Rect(rect.x + index * rect.width / count - 1.2,
                              rect.y + rect.height * .267,
                              2.4, rect.height * .40))
        sep.style = {"fill": BLUE, "stroke_width": 0}
        sep.z_index = 8
    root.metadata["reference_pptx"] = "multi slots(2).pptx"
    root.metadata["reference_fidelity_revision"] = 47
    return True
