from __future__ import annotations

"""Perfil supervisionado de UM ItemSlot azul com uma ou duas etiquetas de preco.

Referencia revisada: Papel Hig Fofinho / clube, 447x345. As proporcoes
sao normalizadas; o teste visual permanece necessario antes da distribuicao.

Esta criacao e opt-in pelo menu ItemSlot; nao modifica a deteccao global do
PPTX, nao substitui SmartSlots importados e nao altera o formato .srscene.
"""

from copy import deepcopy
from typing import Any

from .model import BindingRole, GraphicsNode, NodeKind, Rect, Transform
from .operations import GraphicsSession, _price_parts

PRESET_ID = "limpeza-blue-v1"
BLUE = "#24518E"  # tom proximo a referencia azul royal
WHITE = "#FFFFFF"

# O preco PRINCIPAL e o do clube, o preco SECUNDARIO e o promocional.
LIMPEZA_PRESET: dict[str, Any] = {
    "id": PRESET_ID,
    "name": "AZUL · 1 OU 2 PREÇOS",
    "width": 418.0,
    "height": 320.0,
    "background": None,  # outer frame does not cover the exposed right margin
    "roles": {
        "name": {
            "bounds": [0.105, 0.012, 0.61, 0.160],
            "style": {"font_family": "Impact", "font_size": 25, "font_size_unit": "pt",
                      "font_weight": 700, "fill": WHITE, "color": WHITE, "align": "center",
                      "v_align": "center", "fit_inside_box": True, "nowrap": False},
        },
        "image": {"bounds": [0.073, 0.250, 0.65, 0.710], "style": {"fit": "contain"}},
        "price": {"bounds": [0.469, 0.570, 0.518, 0.395]},
        "currency": {"bounds": [0.035, 0.29, 0.20, 0.40],
                     "style": {"font_family": "Impact", "font_size": 26, "fill": WHITE, "color": WHITE,
                               "align": "center", "fit_inside_box": True}},
        "integer": {"bounds": [0.235, 0.000, 0.48, 0.865],
                    "style": {"font_family": "Impact", "font_size": 108, "fill": WHITE, "color": WHITE,
                              "align": "center", "fit_inside_box": True}},
        "decimal": {"bounds": [0.695, 0.100, 0.305, 0.35],
                    "style": {"font_family": "Impact", "font_size": 36, "fill": WHITE, "color": WHITE,
                              "align": "center", "fit_inside_box": True}},
        "unit": {"bounds": [0.860, 0.790, 0.125, 0.150],
                 "style": {"font_family": "Impact", "font_size": 26, "fill": WHITE, "color": WHITE,
                           "align": "center", "fit_inside_box": True}},
    },
}

# Dois grupos sobrepostos, sem criar outro SmartSlot.
ROLE_RECTS: dict[str, tuple[float, float, float, float]] = {
    # Normalizado ao card x=12..430 / y=12..332 da referencia 447x345.
    "outer_frame": (0.000, 0.000, 0.750, 0.980),
    "white_panel": (0.026, 0.178, 0.696, 0.755),
    "promotion_background": (0.680, 0.405, 0.244, 0.222),
    "promotion_label": (0.712, 0.419, 0.175, 0.054),
    "promotion_currency": (0.703, 0.490, 0.055, 0.087),
    "promotion_integer": (0.748, 0.455, 0.105, 0.165),
    "promotion_cents": (0.852, 0.462, 0.072, 0.072),
    "promotion_unit": (0.856, 0.539, 0.067, 0.064),
    "club_background": (0.460, 0.569, 0.540, 0.431),
    "club_label": (0.642, 0.936, 0.246, 0.061),
}
# Um retangulo de preço principal e seus valores internos; nada se sobrepoe
# por acidente aos demais nós graças às camadas abaixo.
LAYERS = {
    "outer_frame": -100, "white_panel": -90, "image_backplate": -80,
    "image": 10, "club_background": 30, "promotion_background": 40,
    "currency": 72, "integer": 73, "decimal": 74, "unit": 75,
    "promotion_currency": 82, "promotion_integer": 83,
    "promotion_cents": 84, "promotion_unit": 85,
    "promotion_label": 86, "club_label": 87, "name": 90,
}
PRICE_COMPONENT_RECTS = {
    "currency": (0.035, 0.29, 0.20, 0.40),
    "integer": (0.235, 0.000, 0.48, 0.865),
    "decimal": (0.695, 0.100, 0.305, 0.35),
}
MAIN_PRICE_RECT = (0.469, 0.570, 0.518, 0.395)

PROMOTION_FIELDS = ("promotion_currency", "promotion_integer", "promotion_cents", "promotion_unit")


def _rect(root: Rect, role: str) -> Rect:
    x, y, w, h = ROLE_RECTS[role]
    return Rect(root.x + x * root.width, root.y + y * root.height,
                w * root.width, h * root.height)


def _new_node(page, parent_id: str, role: str, *, text: str = "",
              fill: str = WHITE, radius: float = 0.0, size: float = 20.0,
              z: int = 20) -> GraphicsNode:
    bounds = _rect(page.nodes[parent_id].rect.normalized(), role)
    is_text = bool(text)
    node = GraphicsNode(
        kind=NodeKind.TEXT if is_text else NodeKind.RECT,
        name="LIMPEZA " + role.upper(),
        text=text,
        z_index=z,
        transform=Transform(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height),
        style=(
            {"font_family": "Impact", "font_size": size, "font_size_unit": "pt",
             "font_weight": 700, "fill": fill, "color": fill,
             "align": "center", "v_align": "center", "fit_inside_box": True}
            if is_text else
            {"fill": fill, "stroke": fill, "stroke_width": 0.0, "radius_ratio": radius}
        ),
        metadata={"manual_item_slot_child": True, "limpeza_blue_role": role},
        locked=not is_text,
    )
    page.add_node(node, parent_id=parent_id)
    return node


def create_limpeza_blue_slot(session: GraphicsSession, *, x: float | None = None,
                            y: float | None = None):
    """Cria UM SmartSlot, mantendo subprecos como bindings internos independentes."""
    from .item_slots import create_item_slot

    slot = create_item_slot(session, PRESET_ID, x=x, y=y)
    page = session.page
    root_id = str(slot.metadata["root_node_id"])
    extras: dict[str, list[str]] = {}

    with session.transaction("Aplicar perfil unico Limpeza Azul"):
        # Artwork nao e produto: contornos e paineis nunca viram outros slots.
        background_nodes: list[str] = []
        for role, fill, radius, z in (
            ("outer_frame", BLUE, 0.19, LAYERS["outer_frame"]),
            ("white_panel", WHITE, 0.18, LAYERS["white_panel"]),
            ("promotion_background", BLUE, 0.40, LAYERS["promotion_background"]),
            ("club_background", BLUE, 0.25, LAYERS["club_background"]),
        ):
            background_nodes.append(_new_node(page, root_id, role, fill=fill, radius=radius, z=z).id)

        # O ItemSlot generico ja criou um fundo da area da imagem.
        # Deixe-o branco e retire a borda de placeholder.
        for node_id in slot.metadata.get("decorative_nodes") or []:
            node = page.node(str(node_id))
            if node is not None and node.metadata.get("item_slot_image_backplate"):
                node.style = {"fill": WHITE, "stroke": WHITE, "stroke_width": 0.0, "radius_ratio": 0.15}
                node.z_index = LAYERS["image_backplate"]
                node.visible = False  # painel branco unico, sem hit-test redundante
            if node is not None and node.metadata.get("item_slot_background"):
                node.z_index = LAYERS["outer_frame"]

        labels = (
            ("promotion_label", "NA PROMOÇÃO", 11.0),
            ("club_label", "NO CLUBE SR", 15.0),
            ("promotion_currency", "R$", 18.0),
            ("promotion_integer", "00", 42.0),
            ("promotion_cents", ",00", 19.0),
            ("promotion_unit", "CADA", 10.0),
        )
        for role, value, size in labels:
            node = _new_node(page, root_id, role, text=value, size=size, z=LAYERS[role])
            extras[role] = [node.id]

        slot.metadata["extra_bindings"] = extras
        slot.metadata["limpeza_blue_profile"] = PRESET_ID
        slot.metadata["limpeza_blue_version"] = 1
        slot.metadata["limpeza_blue_nodes"] = background_nodes + [item for ids in extras.values() for item in ids]
        slot.metadata["decorative_nodes"] = list(slot.metadata.get("decorative_nodes") or []) + background_nodes
        slot.metadata["secondary_price_visible"] = True
        slot.metadata["club_visible"] = True
        slot.metadata["promotion_visible"] = True
        slot.metadata["single_slot_contract"] = {"primary": "club", "secondary": "promotion",
                                                 "area_count": 1, "pixel_exact": False}
    upgrade_limpeza_blue_slot(page, slot)
    return slot


def _position(node: GraphicsNode, parent: Rect, relative) -> None:
    x, y, width, height = relative
    node.transform.x = parent.x + x * parent.width
    node.transform.y = parent.y + y * parent.height
    node.transform.width = max(1.0, width * parent.width)
    node.transform.height = max(1.0, height * parent.height)


def upgrade_limpeza_blue_slot(page, slot) -> bool:
    """Migração idempotente dos slots V1 ja salvos, inclusive suas camadas.

    Nenhum nó é criado ou apagado. A fonte Impact é fornecida pelo Windows;
    'Anton' sem instalação estava causando substituição imprevisível no Qt.
    """
    if slot.metadata.get("limpeza_blue_profile") != PRESET_ID:
        return False
    if int(slot.metadata.get("limpeza_blue_version") or 1) >= 2:
        return False
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return False
    card = root.rect.normalized()
    for node_id in page.descendants(root.id):
        node = page.node(node_id)
        if node is None:
            continue
        role = str(node.metadata.get("limpeza_blue_role") or "")
        if role in ROLE_RECTS:
            _position(node, card, ROLE_RECTS[role])
            node.z_index = LAYERS.get(role, node.z_index)
            if node.kind is NodeKind.RECT:
                node.locked = True
                node.style["fill"] = BLUE if role != "white_panel" else WHITE
                node.style["stroke"] = node.style["fill"]
                node.style["radius_ratio"] = {
                    "outer_frame": 0.19, "white_panel": 0.18,
                    "promotion_background": 0.40, "club_background": 0.25,
                }.get(role, 0.0)
            elif node.kind is NodeKind.TEXT:
                node.style["font_family"] = "Impact"
                node.style["font_weight"] = 700
                node.style["fit_inside_box"] = True
                if role == "club_label" and node.text == "NO CLUBE":
                    node.text = "NO CLUBE SR"
                sizes = {
                    "promotion_label": 11.0, "club_label": 15.0,
                    "promotion_currency": 18.0, "promotion_integer": 42.0,
                    "promotion_cents": 19.0, "promotion_unit": 10.0,
                }
                node.style["font_size"] = sizes.get(role, 20.0)

    role_nodes = slot.node_by_role
    image = page.node(str(role_nodes.get(BindingRole.IMAGE.value) or ""))
    if image is not None:
        _position(image, card, LIMPEZA_PRESET["roles"]["image"]["bounds"])
        image.z_index = LAYERS["image"]
        image.style["fit"] = "contain" if not image.style.get("fit") else image.style["fit"]
    name = page.node(str(role_nodes.get(BindingRole.NAME.value) or ""))
    if name is not None:
        _position(name, card, LIMPEZA_PRESET["roles"]["name"]["bounds"])
        name.z_index = LAYERS["name"]
        name.style.update(deepcopy(LIMPEZA_PRESET["roles"]["name"]["style"]))
    unit = page.node(str(role_nodes.get(BindingRole.UNIT.value) or ""))
    if unit is not None:
        _position(unit, card, LIMPEZA_PRESET["roles"]["unit"]["bounds"])
        unit.z_index = LAYERS["unit"]
        unit.style.update(deepcopy(LIMPEZA_PRESET["roles"]["unit"]["style"]))

    price = page.node(str((slot.metadata.get("role_area_nodes") or {}).get("price") or ""))
    if price is not None:
        _position(price, card, MAIN_PRICE_RECT)
        price.z_index = 0
        price_rect = price.rect.normalized()
        for field, binding in (
            ("currency", BindingRole.CURRENCY),
            ("integer", BindingRole.PRICE_REAIS),
            ("decimal", BindingRole.PRICE_CENTS),
        ):
            node = page.node(str(role_nodes.get(binding.value) or ""))
            if node is not None:
                _position(node, price_rect, PRICE_COMPONENT_RECTS[field])
                node.z_index = LAYERS[field]
                node.style.update(deepcopy(LIMPEZA_PRESET["roles"][field]["style"]))
    for node_id in slot.metadata.get("decorative_nodes") or []:
        node = page.node(str(node_id))
        if node is None:
            continue
        if node.metadata.get("item_slot_image_backplate"):
            node.visible = False
            node.locked = True
            node.z_index = LAYERS["image_backplate"]
        if node.metadata.get("item_slot_background"):
            node.z_index = LAYERS["outer_frame"]

    slot.metadata["limpeza_blue_version"] = 2
    slot.metadata["limpeza_blue_price_mode"] = "two"
    slot.metadata["single_slot_contract"] = {
        "primary": "club", "secondary": "promotion",
        "area_count": 1, "pixel_exact": False, "layered": True,
    }
    return True



ONE_PRICE_MAIN_RECT = (0.505, 0.565, 0.495, 0.435)
PROMO_NODE_ROLES = (
    "promotion_background", "promotion_label", "promotion_currency",
    "promotion_integer", "promotion_cents", "promotion_unit",
)


def _is_real_price(value: object) -> bool:
    return value is not None and str(value).strip() not in ("", "None")


def _price_variant(product: dict[str, Any]) -> tuple[str, object, object | None]:
    """ONE if there is only one *distinct* price; TWO only for distinct prices."""
    retail = product.get("price")
    club = next((product.get(k) for k in ("club_price", "app_price")
                 if _is_real_price(product.get(k))), None)
    offer = product.get("promotion_price")
    candidates = [v for v in (retail, club, offer) if _is_real_price(v)]
    distinct = []
    for candidate in candidates:
        try:
            numeric = float(str(candidate).strip().replace("R$", "").replace(".", "").replace(",", "."))
        except ValueError:
            numeric = str(candidate).strip().casefold()
        if numeric not in distinct:
            distinct.append(numeric)
    if not candidates:
        return ("one", None, None)
    if len(distinct) <= 1:
        return ("one", retail if _is_real_price(retail) else candidates[0], None)
    # The highlighted price is club or promotional; retail sits in the badge.
    primary = club if _is_real_price(club) else offer
    secondary = retail if _is_real_price(retail) else offer
    return ("two", primary, secondary)


def _apply_price_variant(page, slot, variant: str) -> None:
    """Switch one shared slot between 1/2-price visuals, without new slots."""
    if variant not in ("one", "two"):
        raise ValueError("Invalid price variant")
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        return
    root_rect = root.rect.normalized()
    one = variant == "one"
    for node_id in page.descendants(root.id):
        node = page.node(node_id)
        if node is None:
            continue
        role = str(node.metadata.get("limpeza_blue_role") or "")
        if role in PROMO_NODE_ROLES or role == "club_label":
            node.visible = not one
    main_area = page.node(str((slot.metadata.get("role_area_nodes") or {}).get("price") or ""))
    if main_area is not None:
        _position(main_area, root_rect, ONE_PRICE_MAIN_RECT if one else MAIN_PRICE_RECT)
        area = main_area.rect.normalized()
        for component, binding in (
            ("currency", BindingRole.CURRENCY),
            ("integer", BindingRole.PRICE_REAIS),
            ("decimal", BindingRole.PRICE_CENTS),
        ):
            node = page.node(str(slot.node_by_role.get(binding.value) or ""))
            if node is not None:
                _position(node, area, PRICE_COMPONENT_RECTS[component])
    slot.metadata["limpeza_blue_price_mode"] = variant
    slot.metadata["secondary_price_visible"] = not one
    slot.metadata["promotion_visible"] = not one
    slot.metadata["club_visible"] = not one



def bind_product_to_limpeza_blue_slot(
    session: GraphicsSession, slot_id: str, product: dict[str, Any]
) -> bool:
    """Clube: club_price/app_price/price; promocao: promotion_price/price.

    Cada campo e mapeado para SEU node. Nao escrever preco do clube no selo
    promocional nem sobrescrever o nome com rótulos.
    """
    from .item_slots import bind_product_to_item_slot, refresh_item_slot_metadata

    slot = session.page.slots.get(str(slot_id))
    if slot is None or slot.metadata.get("limpeza_blue_profile") != PRESET_ID:
        return False
    if not isinstance(product, dict):
        return False

    variant, primary, secondary = _price_variant(product)
    payload = deepcopy(product)
    if primary is not None:
        payload["price"] = primary
    if not bind_product_to_item_slot(session, slot.id, payload):
        return False

    extras = slot.metadata.get("extra_bindings") or {}
    unit = str(product.get("unit") or "UN").strip().upper().lstrip("/")
    with session.transaction("Aplicar preço e variação Limpeza Azul"):
        _apply_price_variant(session.page, slot, variant)
        primary_unit = session.page.node(str(slot.node_by_role.get(BindingRole.UNIT.value) or ""))
        if primary_unit is not None:
            primary_unit.text = unit
        if secondary is not None:
            whole, cents = _price_parts(secondary)
            values = {
                "promotion_currency": "R$",
                "promotion_integer": whole,
                "promotion_cents": cents,
                "promotion_unit": str(product.get("promotion_unit") or product.get("unit") or "CADA").strip().upper().lstrip("/"),
            }
            for role, value in values.items():
                for node_id in extras.get(role, []):
                    node = session.page.node(str(node_id))
                    if node is not None and node.kind is NodeKind.TEXT:
                        node.text = str(value)
        for role, value in (
            ("promotion_label", product.get("promotion_label") or "NA PROMOÇÃO"),
            ("club_label", product.get("club_label") or "NO CLUBE SR"),
        ):
            for node_id in extras.get(role, []):
                node = session.page.node(str(node_id))
                if node is not None and node.kind is NodeKind.TEXT:
                    node.text = str(value)
        slot.metadata["limpeza_blue_version"] = max(3, int(slot.metadata.get("limpeza_blue_version") or 1))
        snapshot = slot.metadata.setdefault("product_snapshot", {})
        if isinstance(snapshot, dict):
            snapshot["limpeza_club_price"] = "" if primary is None else str(primary)
            snapshot["limpeza_promotion_price"] = "" if secondary is None else str(secondary)
            snapshot["limpeza_price_variant"] = variant
        refresh_item_slot_metadata(session.page, slot)
    return True


def inspect_limpeza_blue_slot(page, slot) -> dict[str, Any]:
    """Reconhece o contrato do slot criado sem modificar a cena ou criar slots."""
    if slot.metadata.get("limpeza_blue_profile") != PRESET_ID:
        return {"recognized": False, "reason": "profile_mismatch"}
    required = {
        "name": slot.node_by_role.get(BindingRole.NAME.value),
        "image": slot.node_by_role.get(BindingRole.IMAGE.value),
        "club_integer": slot.node_by_role.get(BindingRole.PRICE_REAIS.value),
        "club_cents": slot.node_by_role.get(BindingRole.PRICE_CENTS.value),
    }
    extras = slot.metadata.get("extra_bindings") or {}
    for role in ("promotion_label", "promotion_integer", "promotion_cents", "club_label"):
        ids = extras.get(role, [])
        required[role] = ids[0] if isinstance(ids, list) and ids else None
    missing = sorted(role for role, nid in required.items() if not nid or page.node(str(nid)) is None)
    return {
        "recognized": not missing,
        "profile": PRESET_ID,
        "slot_id": slot.id,
        "missing_roles": missing,
        "role_node_ids": {role: nid for role, nid in required.items() if nid},
    }
