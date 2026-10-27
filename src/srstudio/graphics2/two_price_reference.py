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

PPTX_TWO_PRICE_REVISION = 57
BLUE = "#105594"

# Main price plate, smaller overlapping price badge, and editable labels.
# Individual crop: x=5.04..27.67cm; y=13.8..34.23cm.
# Multi sample: cell spacing 5.61cm, y=26.95..32.84cm, 5 products.
TWO_PRICE_GEOMETRY = {
    "individual-beta44": {
        # Slightly larger than Beta49 while remaining inside the plate.
        "badge": (.477, .832, .237, .148),
        "promo_label": (.486, .850, .214, .038),
        "secondary_price": (.482, .899, .169, .066),
        # Keep club text BELOW digits and LEFT of the unit. No component
        # rectangles intersect even when showing a 3-digit price.
        "club_label": (.713, .905, .185, .048),
        "promotion_unit": (.664, .924, .046, .043),
        # Split promotion like the certified Slot Único: R$ | 32 | ,86.
        "promo_currency": (.488, .910, .038, .054),
        "promo_integer": (.526, .891, .104, .084),
        "promo_cents": (.632, .899, .056, .046),
        "main_price": (.610, .715, .390, .260),
        "currency": (.265, .31, .080, .30),
        "integer": (.355, .13, .370, .60),
        "decimal": (.745, .21, .220, .27),
        "name_panel": (.620, .575, .380, .411),
        "name": (.634, .588, .352, .145),
        "image": (.015, .015, .76, .970),
        "unit": (.910, .918, .070, .065),
    },
    "multi-cell-beta44": {
        # The PPTX mini-badges are narrower and further right in each cell.
        "badge": (.530, .515, .410, .222),
        "promo_label": (.548, .531, .372, .050),
        "secondary_price": (.548, .605, .293, .103),
        "club_label": (.760, .745, .230, .130),
        "promotion_unit": (.849, .650, .071, .050),
        "promo_currency": (.540, .618, .057, .068),
        "promo_integer": (.597, .594, .167, .115),
        "promo_cents": (.767, .600, .077, .061),
        "main_price": (.010, .715, .980, .280),
        # Disjoint money boxes: reais, cents, full NO CLUBE SR and unit.
        "currency": (.055, .290, .160, .440),
        "integer": (.224, .060, .315, .785),
        "decimal": (.550, .165, .168, .290),
        # Original PPTX: unit under cents, left of the rotated club legend.
        "unit": (.549, .895, .165, .085),
        "name": (.015, .018, .970, .175),
        "image": (.045, .210, .910, .465),
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


def _ensure_promotional_unit(page, slot, geometry, enabled: bool):
    """Use the same currency/value/unit anatomy as certified Slot Único."""
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return
    node = page.node(str(slot.metadata.get("promotion_unit_node_id") or ""))
    if node is None:
        node = GraphicsNode(
            kind=NodeKind.TEXT, name="PREÇO PROMOCIONAL · UNIDADE",
            z_index=86, text="UN", transform=Transform(),
            style={"font_family":"Impact", "font_size":10, "font_size_unit":"pt",
                   "font_weight":700, "color":"#FFFFFF", "align":"center",
                   "v_align":"center", "single_line":True, "nowrap":True,
                   "fit_inside_box":True, "min_font_size":6},
            metadata={"manual_item_slot_child":True,
                      "item_slot_role_area":"promotion_unit"},
            visible=False,
        )
        page.add_node(node, parent_id=root.id)
        slot.metadata["promotion_unit_node_id"] = node.id
    unit = page.node(str(slot.node_by_role.get(BindingRole.UNIT.value) or ""))
    node.text = str(unit.text if unit is not None else "UN").lstrip("/")
    _position(node, _absolute(root.rect.normalized(), geometry["promotion_unit"]))
    node.visible = enabled
    node.z_index = 86


def _split_promotional_price(page, slot, geometry, enabled: bool) -> None:
    """Keep the secondary-price binding, but paint 3 independently fitted glyphs.

    Original RETAIL_PRICE node stays in the document for edits and import,
    so switching between one/two prices or reopening a saved scene loses no
    product metadata. Rendering the entire price as one string made centavos
    collide with reais in small Multi badges.
    """
    from .operations import _price_parts

    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return
    source = page.node(str(slot.node_by_role.get(BindingRole.RETAIL_PRICE.value) or ""))
    raw = str(source.text or "") if source is not None else ""
    whole, cents = _price_parts(raw)
    nodes = dict(slot.metadata.get("promotion_amount_nodes") or {})
    for key, value, size in (
        ("promo_currency", "R$", 12.5),
        ("promo_integer", whole, 26.0),
        ("promo_cents", cents, 13.0),
    ):
        node = page.node(str(nodes.get(key) or ""))
        if node is None:
            # Migrates already saved Beta 56/57 cards without duplicating
            # old standalone cards or breaking their original price binding.
            node = next((
                page.node(nid) for nid in page.descendants(root.id)
                if page.node(nid).metadata.get("item_slot_promo_component") == key
            ), None)
        if node is None:
            node = GraphicsNode(
                kind=NodeKind.TEXT,
                name="PROMOÇÃO · " + key.upper(),
                text="", transform=Transform(), z_index=86,
                style={"font_family": "Impact", "font_size": size,
                       "font_size_unit": "pt", "font_weight": 700,
                       "color": "#FFFFFF", "fill": "#FFFFFF",
                       "align": "center", "v_align": "center",
                       "fit_inside_box": True, "single_line": True,
                       "nowrap": True, "wrap": False, "min_font_size": 6},
                metadata={"manual_item_slot_child": True,
                          "item_slot_promo_component": key}, visible=False,
            )
            page.add_node(node, parent_id=root.id)
        nodes[key] = node.id
        node.text = value
        _position(node, _absolute(root.rect.normalized(), geometry[key]))
        node.style["font_size"] = size
        node.style["align"] = "right" if key == "promo_integer" else (
            "left" if key == "promo_cents" else "center")
        node.visible = bool(enabled and value)
        node.z_index = 86
    slot.metadata["promotion_amount_nodes"] = nodes
    # The whole-value binding still receives spreadsheet updates, but
    # displaying it as an additional text node is precisely the overlap bug.
    if source is not None:
        source.visible = False


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
    panel.metadata.pop("transparent_campaign_backplate", None)
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
            name_bounds = geometry["name"] if enabled else (.578, .572, .407, .145)
            _position(name_node, _absolute(root_rect, name_bounds))
            name_node.z_index = 20
    badge = _ensure_badge(page, slot)
    if badge is not None:
        badge.visible = enabled
    _ensure_promotional_unit(page, slot, geometry, enabled)
    _split_promotional_price(page, slot, geometry, enabled)

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
    if preset_id == "multi-cell-beta44":
        from .item_slots import _builtins
        base_name = _builtins()[preset_id].roles["name"]["bounds"]
        name_node = page.node(str(slot.node_by_role.get(BindingRole.NAME.value) or ""))
        if name_node is not None:
            _position(name_node, _absolute(root_rect,
                      geometry["name"] if enabled else base_name))
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
            node.style["pptx_wrap"] = "none"
            if key == "club_label":
                # QML Text.Fit in a narrow group may stack words vertically.
                # This field is an intentional single horizontal line in both
                # source PPTX references, in editor AND PNG/PDF export.
                node.style["single_line"] = True
                node.style["min_font_size"] = 3
                node.style["align"] = "center"
                # Reference Multi: horizontal glyphs rotated as ONE vertical
                # label on the right edge, not stacked letters.
                node.transform.rotation = 90 if preset_id == "multi-cell-beta44" else 0
            # Fonts and target bounds are source-measured: prevent a split
            # NO CLUBE / SR and keep all legends within their own box.
            if key in ("promo_label", "secondary_price"):
                node.style["font_family"] = "Impact"
                node.style["font_weight"] = 700
                node.style["single_line"] = True
            if preset_id == "multi-cell-beta44" and enabled:
                node.style["font_size"] = {
                    "promo_label": 9.0, "secondary_price": 15.0,
                    "club_label": 8.0,
                }[key]
            elif key == "secondary_price":
                node.style["font_size"] = 16.0
            elif key == "club_label":
                node.style["font_size"] = 10.2
        if promo is not None:
            promo.text = "NA PROMOÇÃO"
            promo.visible = True
        if club is not None:
            club.text = "NO CLUBE SR"
            club.visible = True
            club.style["single_line"] = True
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
            if preset_id == "multi-cell-beta44" and enabled:
                # Adjacent box edges alone do not ensure adjacent INK: the
                # former centered glyphs left a variable gap for 1/2 digits.
                node.style["align"] = "right" if key == "integer" else "left" if key == "decimal" else "center"
            elif preset_id == "multi-cell-beta44":
                node.style["align"] = roles[key]["style"].get("align", "center")
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
