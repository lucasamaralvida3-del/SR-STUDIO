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


def _ppt_role(x: float, y: float, w: float, h: float, *, size: float, color: str,
              align: str = "center", weight: int = 700) -> dict[str, Any]:
    """An editable Anton-like source text role with generous fit bounds.

    Measured from individual(1).pptx and multi slots(1).pptx.
    Font fallback is chosen by Qt when Anton is unavailable.
    """
    role = _text_role(x, y, w, h, size=size, weight=weight, align=align)
    # The source uses Anton, but that face is not available on standard
    # Windows installations. Arial is explicitly selected instead of
    # letting Qt render missing-glyph boxes for every price digit.
    # Prefer the *exact* PPTX typeface when the machine has it; Windows
    # includes Impact as a visually close, readable condensed fallback.
    family = "Impact"
    try:
        from PySide6.QtGui import QGuiApplication, QFontDatabase
        if QGuiApplication.instance() is not None:
            if "Anton" in QFontDatabase.families():
                family = "Anton"
    except (ImportError, RuntimeError):
        pass
    role["style"].update({"font_family": family, "source_font_family": "Anton", "color": color,
                           "font_size_unit": "pt", "min_font_size": 7,
                           "fit_inside_box": True, "wrap": True})
    return role


def _format_reference_name(value: str, *, max_chars: int = 19) -> str:
    """Break long catalog descriptions into two source-PPT-like lines.

    Impact/Anton is intentionally condensed but should never produce the
    single unreadable stretched caption seen in the previous Beta45 preview.
    The original name is kept in the slot product snapshot for editing.
    """
    words = str(value or "").strip().split()
    if len(" ".join(words)) <= max_chars or len(words) < 2:
        return " ".join(words)
    options = [(" ".join(words[:index]), " ".join(words[index:]))
               for index in range(1, len(words))]
    front, back = min(options, key=lambda parts: (
        max(len(parts[0]), len(parts[1])),
        abs(len(parts[0])-len(parts[1])),
    ))
    return front + "\n" + back


def _builtins() -> dict[str, ItemSlotPreset]:
    from .slot_limpeza_blue import LIMPEZA_PRESET

    return {
        "limpeza-blue-v1": ItemSlotPreset(**copy.deepcopy(LIMPEZA_PRESET)),
        # PPT reference: dominant product image, blue uppercase name and
        # overlapping solid-blue bottom-right price plate (without gray boxes).
        # Keep Beta44 IDs to migrate saved layouts in place.
        "individual-beta44": ItemSlotPreset(
            id="individual-beta44",
            name="INDIVIDUAL PROMOCIONAL",
            width=460,
            height=510,
            background={"fill": "#FFFFFF", "stroke": "none", "stroke_width": 0},
            roles={
                "image": {"bounds": [.005, .005, .41, .985],
                          "style": {"fit": "contain"}},
                "name": _ppt_role(.555, .535, .435, .155, size=27,
                                  color="#105594", align="center"),
                "price": {"bounds": [.525, .722, .475, .269],
                          "background": {"fill": "#105594", "stroke_width": 0,
                                         "radius_ratio": .13}},
                "currency": _ppt_role(.07, .52, .23, .37, size=39, color="#FFFFFF"),
                "integer": _ppt_role(.27, .31, .45, .70, size=91, color="#FFFFFF"),
                "decimal": _ppt_role(.72, .29, .26, .29, size=30, color="#FFFFFF"),
                "unit": _ppt_role(.81, .89, .17, .08, size=20, color="#FFFFFF"),
                "secondary_price": _ppt_role(.55, .73, .23, .05, size=12,
                                             color="#FFFFFF"),
                "limit": _ppt_role(.53, .988, .47, .028, size=9, color="#105594"),
                "club_label": _ppt_role(.80, .73, .18, .06, size=10,
                                        color="#FFFFFF"),
                "promotion_label": _ppt_role(.63, .73, .32, .05, size=20,
                                             color="#FFFFFF"),
            },
        ),
        # One source 5-column strip, reused for 6 columns without changing
        # aspect, product spacing or blue footer proportion.
        "multi-cell-beta44": ItemSlotPreset(
            id="multi-cell-beta44",
            name="ITEM DA FAIXA PROMOCIONAL",
            width=194,
            height=300,
            background=None,  # the parent owns the continuous blue footer
            roles={
                "name": _ppt_role(.015, .085, .97, .17, size=16,
                                  color="#105594"),
                "image": {"bounds": [.08, .28, .84, .48],
                          "style": {"fit": "contain"}},
                "price": {"bounds": [.01, .805, .98, .19]},
                "currency": _ppt_role(.035, .27, .20, .54, size=17, color="#FFFFFF"),
                "integer": _ppt_role(.245, .045, .47, .90, size=46, color="#FFFFFF"),
                "decimal": _ppt_role(.695, .17, .29, .33, size=18, color="#FFFFFF"),
                "unit": _ppt_role(.75, .944, .215, .052, size=11, color="#FFFFFF"),
                "secondary_price": _ppt_role(.05, .768, .48, .035,
                                             size=9, color="#FFFFFF"),
                "club_label": _ppt_role(.55, .768, .43, .035,
                                        size=8, color="#FFFFFF"),
                "promotion_label": _ppt_role(.20, .767, .60, .035,
                                             size=8, color="#FFFFFF"),
            },
        ),
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
    # Beta 40: one supported *creation* template, with automatic price variants.
    # Keep legacy presets in _builtins() for opening already saved documents.
    # Legacy Quinta3 families remain addressable to preserve existing
    # projects and their supported programmatic creation contracts. The
    # Beta44 visual picker intentionally displays only its three core styles.
    visible = ["limpeza-blue-v1", "multi-cell-beta44", "individual-beta44"]
    historical = [key for key in presets if key.startswith("quinta3-")]
    return [presets[key] for key in visible + historical]


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
                style=copy.deepcopy(background_style),
                metadata={"manual_item_slot_child": True, "item_slot_background": True},
            )
            _add_node(page, background, root.id)
            background_id = background.id

        image_spec = dict(roles.get("image") or {})
        image_rect = _absolute(root_rect, list(image_spec.get("bounds") or [0.1, 0.2, 0.8, 0.45]))
        # Reference art has NO visible gray placeholder frame. It is the
        # actual product image on white paper, not a UI-style picture input.
        source_faithful = preset_id in ("individual-beta44", "multi-cell-beta44")
        image_backplate = None
        if not source_faithful:
            image_backplate = GraphicsNode(
                kind=NodeKind.RECT,
                name="IMAGE AREA",
                transform=Transform(x=image_rect.x, y=image_rect.y, width=image_rect.width, height=image_rect.height),
                style={"fill": "#F8FAFC", "stroke": "#CBD5E1", "stroke_width": 1.0, "radius_ratio": 0.04},
                metadata={"manual_item_slot_child": True, "item_slot_image_backplate": True},
            )
            _add_node(page, image_backplate, root.id)
        image = GraphicsNode(
            kind=NodeKind.IMAGE,
            name="IMAGE ROLE",
            transform=Transform(x=image_rect.x, y=image_rect.y, width=image_rect.width, height=image_rect.height),
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
            metadata={"manual_item_slot_child": True, "item_slot_role_area": "price"},
        )
        _add_node(page, price_group, root.id)
        price_background_id = ""
        if isinstance(price_spec.get("background"), dict):
            price_bg = GraphicsNode(
                kind=NodeKind.RECT,
                name="PRICE BACKGROUND",
                transform=Transform(x=price_rect.x, y=price_rect.y, width=price_rect.width, height=price_rect.height),
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
            comp_style = dict(spec.get("style") or {})
            if dict(price_spec.get("background") or {}).get("fill") == "#265398":
                comp_style.setdefault("color", "#FFFFFF")
            node = _make_text(page, price_group.id, f"PRICE {label}", placeholder,
                              component_rect, comp_style, binding)
            node.metadata["item_slot_price_component"] = key
            component_nodes[key] = node

        unit_spec = dict(roles.get("unit") or {})
        unit_rect = _absolute(root_rect, list(unit_spec.get("bounds") or [0.78, 0.8, 0.18, 0.1]))
        unit = _make_text(page, root.id, "UNIT ROLE", "UN", unit_rect, dict(unit_spec.get("style") or {}), BindingRole.UNIT)
        unit.metadata["item_slot_role_area"] = "unit"

        # Optional fields are real editable text nodes; they are kept in the
        # slot binding map so save/load and normal product binding work.
        optional_nodes: dict[str, GraphicsNode] = {}
        for key, role, placeholder in (
            ("secondary_price", BindingRole.RETAIL_PRICE, "R$ 00,00"),
            ("limit", BindingRole.LIMIT, ""),
        ):
            if key not in roles:
                continue
            spec = dict(roles[key])
            bounds = _absolute(root_rect, list(spec.get("bounds") or [0, 0, 1, 1]))
            node = _make_text(page, root.id, key.upper(), placeholder,
                              bounds, dict(spec.get("style") or {}), role)
            node.visible = False
            node.metadata["item_slot_role_area"] = key
            optional_nodes[role.value] = node

        promotion_label = None
        if "promotion_label" in roles:
            spec = dict(roles["promotion_label"])
            bounds = _absolute(root_rect, list(spec["bounds"]))
            promotion_label = _make_text(
                page, root.id, "PROMOTION LABEL", "PROMOÇÃO" if preset_id == "individual-beta44" else "NA PROMOÇÃO",
                bounds, dict(spec.get("style") or {}))
            promotion_label.metadata["item_slot_role_area"] = "promotion_label"

        club_label = None
        if "club_label" in roles:
            spec = dict(roles["club_label"])
            bounds = _absolute(root_rect, list(spec.get("bounds") or [0, 0, 1, 1]))
            club_label = _make_text(
                page, root.id, "CLUB LABEL", "NO CLUBE SR",
                bounds, dict(spec.get("style") or {}))
            club_label.visible = False
            club_label.metadata["item_slot_role_area"] = "club_label"

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
                **{role: node.id for role, node in optional_nodes.items()},
            },
            confidence=1.0,
            metadata={
                "source": ITEM_SLOT_SOURCE,
                "manual_item_slot": True,
                "preset_id": str(preset.get("id") or preset_id),
                "root_node_id": root.id,
                "role_area_nodes": {"image": image.id, "name": name_node.id, "price": price_group.id, "unit": unit.id},
                "decorative_nodes": [item for item in (background_id, image_backplate.id if image_backplate else "", price_background_id) if item],
                "price_block": {
                    "currency_node": component_nodes["currency"].id,
                    "integer_node": component_nodes["integer"].id,
                    "decimal_node": component_nodes["decimal"].id,
                    "unit_node": unit.id,
                    "combined_value": "",
                },
                "state": "empty",
                "reference_fidelity_revision": 46 if source_faithful else 1,
                "reference_source": ("individual(1).pptx" if preset_id == "individual-beta44"
                                     else "multi slots(1).pptx") if source_faithful else "",
                "product_snapshot": {},
                "price_mode": "auto",
                "price_variant": "one",
                "club_label_node_id": club_label.id if club_label is not None else "",
                "promotion_label_node_id": promotion_label.id if promotion_label is not None else "",
            },
        )
        # The scene painter sorts ALL nodes by z_index globally. Without
        # explicit layers, UUID ordering made white backgrounds cover prices
        # and text appear behind a random card.
        for node_id in page.descendants(root.id):
            layer = page.node(node_id)
            if layer is None:
                continue
            if layer.metadata.get("item_slot_background"):
                layer.z_index = -70
            elif layer.metadata.get("item_slot_image_backplate"):
                layer.z_index = -40
            elif layer.metadata.get("item_slot_price_background"):
                layer.z_index = 30
            elif layer.kind is NodeKind.IMAGE:
                layer.z_index = 10
            elif layer.kind is NodeKind.TEXT:
                layer.z_index = 50 if (layer.binding_role not in (BindingRole.NAME,)) else 20

        root.metadata["item_slot_id"] = slot.id
        root.metadata["reference_fidelity_revision"] = 46 if source_faithful else 1
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
    # Upgrade legacy Limpeza V1 once on load without creating extra slots.
    # Version 2 is idempotent; later payload refreshes are effectively O(1).
    from .slot_limpeza_blue import upgrade_limpeza_blue_slot
    from .reference_fidelity import migrate_reference_slot, migrate_multi_parent
    presets = _builtins()

    for page in document.pages:
        for node in list(page.nodes.values()):
            if node.metadata.get("multi_slot_beta44"):
                migrate_multi_parent(page, node.id)
        for slot in page.slots.values():
            if slot.metadata.get("limpeza_blue_profile"):
                upgrade_limpeza_blue_slot(page, slot)
            migrate_reference_slot(page, slot, presets)
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
    # Product-free duplicates must not retain secondary promotion amounts.
    extra_placeholders = {
        "promotion_integer": "00", "promotion_cents": ",00",
        "promotion_currency": "R$", "promotion_unit": "CADA",
        "app_price_integer": "00", "app_price_cents": ",00",
        "app_price_currency": "R$", "app_unit": "UN",
    }
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for role, value in extra_placeholders.items():
            for node_id in extras.get(role, []):
                node = page.node(str(node_id))
                if node is not None and node.kind is NodeKind.TEXT:
                    node.text = value
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
        original_club_label = str(source_slot.metadata.get("club_label_node_id") or "")
        if original_club_label:
            clone.metadata["club_label_node_id"] = mapping.get(original_club_label, "")
        old_promotion = str(source_slot.metadata.get("promotion_label_node_id") or "")
        if old_promotion:
            clone.metadata["promotion_label_node_id"] = mapping.get(old_promotion, "")
        # Duplicating one cell produces a standalone card, not a reference
        # to the parent strip. The original multi strip stays untouched.
        for key in ("multi_parent_id", "multi_index", "multi_count"):
            clone.metadata.pop(key, None)
        # Secondary price and label nodes must belong to the NEW tree.
        extras = source_slot.metadata.get("extra_bindings")
        if isinstance(extras, dict):
            clone.metadata["extra_bindings"] = {
                role: [mapping[node_id] for node_id in raw if node_id in mapping]
                for role, raw in extras.items() if isinstance(raw, (list, tuple))
            }
        if isinstance(source_slot.metadata.get("limpeza_blue_nodes"), list):
            clone.metadata["limpeza_blue_nodes"] = [
                mapping[node_id] for node_id in source_slot.metadata["limpeza_blue_nodes"] if node_id in mapping
            ]
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
    preset_id = str(slot.metadata.get("preset_id") or "")
    if preset_id in ("individual-beta44", "multi-cell-beta44"):
        # Automatic 1/2-price variation shares the price parsing semantics
        # with the certified Azul slot, but keeps individual item bindings.
        from .slot_limpeza_blue import _price_variant
        variant, primary, secondary = _price_variant(product)
        mode = str(slot.metadata.get("price_mode") or "auto")
        if mode not in ("auto", "one", "two"):
            mode = "auto"
        display_two = variant == "two" if mode == "auto" else mode == "two"
        payload = copy.deepcopy(product)
        if primary is not None:
            payload["price"] = primary
        payload["retail_price"] = secondary if secondary is not None else ""
        session.bind_product(slot.id, payload)
        name_node = session.page.node(str(slot.node_by_role.get(BindingRole.NAME.value) or ""))
        if name_node is not None:
            raw_name = str(payload.get("display_name") or payload.get("name") or
                           payload.get("original_name") or name_node.text or "")
            name_node.text = _format_reference_name(
                raw_name, max_chars=19 if preset_id == "multi-cell-beta44" else 18)
        # The reference text is "UN", never "/UN". Keep the generic
        # GraphicsSession price binding intact for other slot families.
        unit_node = session.page.node(str(slot.node_by_role.get(BindingRole.UNIT.value) or ""))
        if unit_node is not None:
            unit_node.text = str(product.get("unit") or "UN").upper().strip().lstrip("/")
        secondary_node = session.page.node(str(slot.node_by_role.get(BindingRole.RETAIL_PRICE.value) or ""))
        limit_node = session.page.node(str(slot.node_by_role.get(BindingRole.LIMIT.value) or ""))
        if secondary_node is not None:
            secondary_node.visible = display_two
            if display_two and secondary is None:
                secondary_node.text = "R$ 00,00"
        if limit_node is not None:
            limit_value = str(product.get("cpf_limit") or product.get("limit") or "").strip()
            unit = str(product.get("unit") or "UN").strip().upper().lstrip("/")
            if limit_value:
                limit_node.text = f"LIMITE DE {limit_value} {unit} POR CPF"
            limit_node.visible = bool(limit_value)
        club_label = session.page.node(str(slot.metadata.get("club_label_node_id") or ""))
        if club_label is not None:
            club_label.visible = display_two and bool(product.get("club_price") or product.get("app_price"))
        promotional_label = session.page.node(str(slot.metadata.get("promotion_label_node_id") or ""))
        if promotional_label is not None:
            promotional_label.visible = not display_two
        slot.metadata["price_variant"] = "two" if display_two else "one"
    else:
        session.bind_product(slot.id, product)
    for node_id in slot.node_by_role.values():
        node = session.page.node(node_id)
        if node is not None and node.binding_role is BindingRole.IMAGE and slot.product_id:
            node.metadata["placeholder"] = False
    refresh_item_slot_metadata(session.page, slot)
    return True
