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

PPTX_TWO_PRICE_REVISION = 50
BLUE = "#105594"

# Main price plate, smaller overlapping price badge, and editable labels.
# Individual crop: x=5.04..27.67cm; y=13.8..34.23cm.
# Multi sample: cell spacing 5.61cm, y=26.95..32.84cm, 5 products.
TWO_PRICE_GEOMETRY = {
    "individual-beta44": {
        # Slightly larger than Beta49 while remaining inside the plate.
        "badge": (.529, .879, .167, .110),
        "promo_label": (.539, .887, .148, .035),
        "secondary_price": (.536, .922, .152, .061),
        "club_label": (.720, .931, .230, .048),
        "main_price": (.610, .715, .390, .260),
        "name_panel": (.620, .575, .380, .411),
        "name": (.634, .588, .352, .145),
        "image": (.015, .015, .76, .970),
        "unit": (.898, .846, .075, .085),
    },
    "multi-cell-beta44": {
        # The PPTX mini-badges are narrower and further right in each cell.
        "badge": (.572, .538, .338, .194),
        "promo_label": (.578, .548, .322, .051),
        "secondary_price": (.583, .612, .314, .101),
        "club_label": (.589, .819, .335, .076),
        "main_price": (.010, .715, .980, .280),
        # Two-price main digits stop before NO CLUBE SR.
        "currency": (.052, .200, .148, .420),
        "integer": (.203, .037, .335, .807),
        "decimal": (.548, .122, .150, .335),
        "unit": (.770, .911, .159, .072),
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
    badge.style["radius_ratio"] = .24
    badge.z_index = 38
    return badge


def ensure_individual_name_panel(page, slot, *, two_prices=False):
    """Create the source-white name background between image and editable title.

    Beta49 already has saved slots: never duplicate the panel when reopening
    them. It is decorative, so neither SKU nor image data is altered.
    """
    if str(slot.metadata.get("preset_id") or "") != "individual-beta44":
        return None
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return None
    panel = page.node(str(slot.metadata.get("name_backdrop_node_id") or ""))
    if panel is None:
        panel = GraphicsNode(
            kind=NodeKind.RECT,
            name="PPTX INDIVIDUAL · WHITE NAME BACKGROUND",
            z_index=15, transform=Transform(),
            style={"fill": "#FFFFFF", "stroke": "none", "stroke_width": 0,
                   "radius_ratio": .09},
            metadata={"manual_item_slot_child": True,
                      "item_slot_name_backdrop": True},
        )
        page.add_node(panel, parent_id=root.id)
        slot.metadata["name_backdrop_node_id"] = panel.id
    bounds = (TWO_PRICE_GEOMETRY["individual-beta44"]["name_panel"]
              if two_prices else (.552, .563, .448, .415))
    _position(panel, _absolute(root.rect.normalized(), bounds))
    panel.z_index = 15
    panel.visible = True
    return panel


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
    if preset_id == "individual-beta44":
        ensure_individual_name_panel(page, slot, two_prices=enabled)
        name_node = page.node(str(slot.node_by_role.get(BindingRole.NAME.value) or ""))
        if name_node is not None:
            from .item_slots import _builtins
            base_name = _builtins()[preset_id].roles["name"]["bounds"]
            name_bounds = geometry["name"] if enabled else base_name
            _position(name_node, _absolute(root_rect, name_bounds))
            name_node.z_index = 20
    badge = _ensure_badge(page, slot)
    if badge is not None:
        badge.visible = enabled

    # The two-price Individual PPTX shows ONE large product cutout. The
    # earlier one-price file shows the repeated cutouts; switching modes must
    # restore them without replacing or dropping the SKU image.
    primary = page.node(str(slot.node_by_role.get(BindingRole.IMAGE.value) or ""))
    repeated = page.node(str(slot.metadata.get("image_repeat_node_id") or ""))
    if primary is not None:
        from .item_slots import _builtins
        base_image = _builtins()[preset_id].roles["image"]["bounds"]
        chosen_image = geometry.get("image", base_image) if enabled else base_image
        _position(primary, _absolute(root_rect, chosen_image))
    if repeated is not None:
        _position(repeated, _absolute(root_rect, (.236, .005, .41, .985)))
        repeated.visible = (not enabled) and bool(
            repeated.asset_id or repeated.metadata.get("bound_image_source"))

    # All three text pieces remain editable text nodes in their original slot.
    promo = page.node(str(slot.metadata.get("promotion_label_node_id") or ""))
    club = page.node(str(slot.metadata.get("club_label_node_id") or ""))
    secondary = page.node(str(slot.node_by_role.get(BindingRole.RETAIL_PRICE.value) or ""))

    if enabled:
        for node, key, z, min_size in (
            (promo, "promo_label", 82, 3.5),
            (secondary, "secondary_price", 83, 5.5),
            (club, "club_label", 84, 3.5),
        ):
            if node is None:
                continue
            _position(node, _absolute(root_rect, geometry[key]))
            node.z_index = z
            node.style["color"] = "#FFFFFF"
            node.style["fill"] = "#FFFFFF"
            node.style["fit_inside_box"] = True
            node.style["min_font_size"] = min_size
            node.style["nowrap"] = True
            node.style["wrap"] = False
            # Fonts and target bounds are source-measured: prevent a split
            # NO CLUBE / SR and keep all legends within their own box.
            if preset_id == "multi-cell-beta44":
                node.style["font_size"] = {
                    "promo_label": 7.0, "secondary_price": 9.2,
                    "club_label": 7.1,
                }[key]
            elif key == "secondary_price":
                node.style["font_size"] = 13.0
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
            spec = geometry[key] if enabled and key in geometry else roles[key]["bounds"]
            _position(node, _absolute(price_rect, spec))
    for node_id in slot.metadata.get("decorative_nodes") or []:
        node = page.node(str(node_id))
        if node is not None and node.metadata.get("item_slot_price_background"):
            _position(node, price_rect)
    unit = page.node(str(slot.node_by_role.get(BindingRole.UNIT.value) or ""))
    if unit is not None:
        unit_box = geometry.get("unit", roles["unit"]["bounds"]) if enabled else roles["unit"]["bounds"]
        _position(unit, _absolute(root_rect, unit_box))
        if enabled:
            unit.z_index = 85

    slot.metadata["two_price_reference_revision"] = PPTX_TWO_PRICE_REVISION
    slot.metadata["two_price_reference_source"] = (
        "INDIVIDUAL DOIS PRECOS.pptx" if preset_id == "individual-beta44"
        else "MULTI SLOTS DOIS PR~ÇOS.pptx"
    )
    return True
