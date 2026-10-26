from __future__ import annotations

"""Actual two-price overlay geometry from the user's PowerPoint files.

Sources: INDIVIDUAL DOIS PRECOS.pptx, MULTI SLOTS DOIS PR~ÇOS.pptx.
PPTX coordinates were measured in centimetres, then normalized to the
canonical editable Individual and Multi-cell roots. The small badge and large
club-price plate are pieces of ONE Smart Slot, never an independent new slot.

Existing 1-price composition remains unchanged; this module only shows
extra artwork when mode='two'.
"""

from .model import BindingRole, GraphicsNode, NodeKind, Rect, Transform

PPTX_TWO_PRICE_REVISION = 49
BLUE = "#105594"

# Main price plate, smaller overlapping price badge, and editable labels.
# Individual crop: x=5.04..27.67cm; y=13.8..34.23cm.
# Multi sample: cell spacing 5.61cm, y=26.95..32.84cm, 5 products.
TWO_PRICE_GEOMETRY = {
    "individual-beta44": {
        "badge": (.540, .896, .145, .094),
        "promo_label": (.542, .899, .140, .032),
        "secondary_price": (.542, .929, .140, .056),
        "club_label": (.720, .933, .230, .045),
        "main_price": (.610, .715, .390, .260),
    },
    "multi-cell-beta44": {
        "badge": (.465, .524, .375, .220),
        "promo_label": (.465, .554, .365, .045),
        "secondary_price": (.475, .611, .350, .105),
        "club_label": (.460, .818, .460, .116),
        "main_price": (.010, .715, .980, .280),
    },
}


def _absolute(root: Rect, values) -> Rect:
    x, y, width, height = values
    return Rect(root.x + root.width * x, root.y + root.height * y,
                root.width * width, root.height * height)


def _position(node, rect: Rect) -> None:
    if node is None:
        return
    node.transform.x = rect.x
    node.transform.y = rect.y
    node.transform.width = max(.1, rect.width)
    node.transform.height = max(.1, rect.height)


def _ensure_badge(page, slot):
    """Repair an existing saved slot in place without losing its product."""
    root_id = str(slot.metadata.get("root_node_id") or "")
    root = page.node(root_id)
    if root is None:
        return None
    badge = page.node(str(slot.metadata.get("two_price_badge_node_id") or ""))
    if badge is None:
        badge = GraphicsNode(
            kind=NodeKind.RECT,
            name="PPTX TWO PRICE · BLUE PROMOTION BADGE",
            z_index=38,
            transform=Transform(),
            style={"fill": BLUE, "stroke": "none", "stroke_width": 0,
                   "radius_ratio": .27},
            metadata={"manual_item_slot_child": True,
                      "item_slot_two_price_badge": True},
            visible=False,
        )
        page.add_node(badge, parent_id=root.id)
        slot.metadata["two_price_badge_node_id"] = badge.id
    _position(badge, _absolute(root.rect.normalized(),
                               TWO_PRICE_GEOMETRY[slot.metadata["preset_id"]]["badge"]))
    badge.z_index = 38
    return badge


def apply_two_price_layout(page, slot, enabled: bool) -> bool:
    """Switch only art and geometry; caller owns price values and undo scope."""
    preset_id = str(slot.metadata.get("preset_id") or "")
    geometry = TWO_PRICE_GEOMETRY.get(preset_id)
    if geometry is None:
        return False
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return False
    root_rect = root.rect.normalized()
    badge = _ensure_badge(page, slot)
    if badge is not None:
        badge.visible = enabled

    # All three text pieces remain editable text nodes in their original slot.
    promo = page.node(str(slot.metadata.get("promotion_label_node_id") or ""))
    club = page.node(str(slot.metadata.get("club_label_node_id") or ""))
    secondary = page.node(str(slot.node_by_role.get(BindingRole.RETAIL_PRICE.value) or ""))

    if enabled:
        for node, key, z, min_size in (
            (promo, "promo_label", 82, 6.5),
            (secondary, "secondary_price", 83, 8.5),
            (club, "club_label", 84, 7.0),
        ):
            if node is None:
                continue
            _position(node, _absolute(root_rect, geometry[key]))
            node.z_index = z
            node.style["color"] = "#FFFFFF"
            node.style["fill"] = "#FFFFFF"
            node.style["fit_inside_box"] = True
            node.style["min_font_size"] = min_size
        if promo is not None:
            promo.text = "NA PROMOÇÃO"
            promo.visible = True
        if club is not None:
            club.text = "NO CLUBE SR"
            club.visible = True
    else:
        # The 1-price template must not inherit the 2-price text positions.
        from .item_slots import _builtins
        roles = _builtins()[preset_id].roles
        for node, key in ((promo, "promotion_label"), (club, "club_label"),
                          (secondary, "secondary_price")):
            if node is not None and key in roles:
                _position(node, _absolute(root_rect, roles[key]["bounds"]))
                node.style = dict(roles[key]["style"])
        if promo is not None:
            promo.text = "PROMOÇÃO" if preset_id == "individual-beta44" else "NA PROMOÇÃO"
            promo.visible = True
        if club is not None:
            club.visible = False
        if secondary is not None:
            secondary.visible = False

    # In the two-price PPTX, the large plate belongs to the CLUB price.
    # Reposition that existing group and its editable components, not a copy.
    from .item_slots import _builtins
    roles = _builtins()[preset_id].roles
    plate_bounds = geometry["main_price"] if enabled else roles["price"]["bounds"]
    price_rect = _absolute(root_rect, plate_bounds)
    price = page.node(str(slot.metadata.get("role_area_nodes", {}).get("price") or ""))
    _position(price, price_rect)
    for role, key in ((BindingRole.CURRENCY, "currency"),
                      (BindingRole.PRICE_REAIS, "integer"),
                      (BindingRole.PRICE_CENTS, "decimal")):
        node = page.node(str(slot.node_by_role.get(role.value) or ""))
        if node is not None:
            _position(node, _absolute(price_rect, roles[key]["bounds"]))
    for node_id in slot.metadata.get("decorative_nodes") or []:
        node = page.node(str(node_id))
        if node is not None and node.metadata.get("item_slot_price_background"):
            _position(node, price_rect)

    slot.metadata["two_price_reference_revision"] = PPTX_TWO_PRICE_REVISION
    slot.metadata["two_price_reference_source"] = (
        "INDIVIDUAL DOIS PRECOS.pptx" if preset_id == "individual-beta44"
        else "MULTI SLOTS DOIS PR~ÇOS.pptx"
    )
    return True
