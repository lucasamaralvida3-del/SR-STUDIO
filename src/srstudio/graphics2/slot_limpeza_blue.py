from __future__ import annotations

"""Perfil supervisionado de UM ItemSlot de limpeza (azul, dois precos).

Referencia visual: arte fornecida pelo usuario, 960x800. Coordenadas abaixo
sao NORMALIZADAS ao card visual x=40..907 / y=60..724; servem como ponto
de partida editavel, nao como afirmacao de fidelidade pixel-a-pixel ao PPTX.

Esta criacao e opt-in pelo menu ItemSlot; nao modifica a deteccao global do
PPTX, nao substitui SmartSlots importados e nao altera o formato .srscene.
"""

from copy import deepcopy
from typing import Any

from .model import BindingRole, GraphicsNode, NodeKind, Rect, Transform
from .operations import GraphicsSession, _price_parts

PRESET_ID = "limpeza-blue-v1"
BLUE = "#155A98"
WHITE = "#FFFFFF"

# O preco PRINCIPAL e o do clube, o preco SECUNDARIO e o promocional.
LIMPEZA_PRESET: dict[str, Any] = {
    "id": PRESET_ID,
    "name": "LIMPEZA · AZUL · 2 PRECOS",
    "width": 867.0,
    "height": 664.0,
    "background": None,  # outer frame does not cover the exposed right margin
    "roles": {
        "name": {
            "bounds": [0.09, 0.025, 0.66, 0.145],
            "style": {"font_family": "Anton", "font_size": 21, "font_size_unit": "pt",
                      "font_weight": 700, "fill": WHITE, "color": WHITE, "align": "center",
                      "v_align": "center", "fit_inside_box": True, "nowrap": False},
        },
        "image": {"bounds": [0.10, 0.28, 0.53, 0.56], "style": {"fit": "contain"}},
        "price": {"bounds": [0.48, 0.67, 0.50, 0.28]},
        "currency": {"bounds": [0.02, 0.24, 0.18, 0.52],
                     "style": {"font_family": "Anton", "font_size": 26, "fill": WHITE, "color": WHITE,
                               "align": "center", "fit_inside_box": True}},
        "integer": {"bounds": [0.18, 0.00, 0.53, 0.96],
                    "style": {"font_family": "Anton", "font_size": 100, "fill": WHITE, "color": WHITE,
                              "align": "center", "fit_inside_box": True}},
        "decimal": {"bounds": [0.70, 0.04, 0.30, 0.38],
                    "style": {"font_family": "Anton", "font_size": 38, "fill": WHITE, "color": WHITE,
                              "align": "center", "fit_inside_box": True}},
        "unit": {"bounds": [0.86, 0.83, 0.12, 0.11],
                 "style": {"font_family": "Anton", "font_size": 27, "fill": WHITE, "color": WHITE,
                           "align": "center", "fit_inside_box": True}},
    },
}

# Dois grupos sobrepostos, sem criar outro SmartSlot.
ROLE_RECTS: dict[str, tuple[float, float, float, float]] = {
    "outer_frame": (0.000, 0.000, 0.747, 0.977),
    "white_panel": (0.027, 0.180, 0.694, 0.767),
    "promotion_background": (0.540, 0.420, 0.215, 0.203),
    "promotion_label": (0.580, 0.432, 0.137, 0.051),
    "promotion_currency": (0.545, 0.497, 0.043, 0.064),
    "promotion_integer": (0.594, 0.482, 0.108, 0.095),
    "promotion_cents": (0.695, 0.479, 0.066, 0.051),
    "promotion_unit": (0.685, 0.551, 0.068, 0.053),
    "club_background": (0.460, 0.572, 0.540, 0.428),
    "club_label": (0.628, 0.593, 0.186, 0.050),
}
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
            {"font_family": "Anton", "font_size": size, "font_size_unit": "pt",
             "font_weight": 700, "fill": fill, "color": fill,
             "align": "center", "v_align": "center", "fit_inside_box": True}
            if is_text else
            {"fill": fill, "stroke": fill, "stroke_width": 0.0, "radius_ratio": radius}
        ),
        metadata={"manual_item_slot_child": True, "limpeza_blue_role": role},
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
            ("outer_frame", BLUE, 0.15, -100),
            ("white_panel", WHITE, 0.20, -70),
            ("promotion_background", BLUE, 0.32, -50),
            ("club_background", BLUE, 0.18, -40),
        ):
            background_nodes.append(_new_node(page, root_id, role, fill=fill, radius=radius, z=z).id)

        # O ItemSlot generico ja criou um fundo da area da imagem.
        # Deixe-o branco e retire a borda de placeholder.
        for node_id in slot.metadata.get("decorative_nodes") or []:
            node = page.node(str(node_id))
            if node is not None and node.metadata.get("item_slot_image_backplate"):
                node.style = {"fill": WHITE, "stroke": WHITE, "stroke_width": 0.0, "radius_ratio": 0.15}
                node.z_index = -60
            if node is not None and node.metadata.get("item_slot_background"):
                node.z_index = -100

        labels = (
            ("promotion_label", "NA PROMOÇÃO", 12.0),
            ("club_label", "NO CLUBE", 22.0),
            ("promotion_currency", "R$", 20.0),
            ("promotion_integer", "00", 40.0),
            ("promotion_cents", ",00", 22.0),
            ("promotion_unit", "CADA", 12.0),
        )
        for role, value, size in labels:
            node = _new_node(page, root_id, role, text=value, size=size)
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
    return slot


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

    primary = next((product[key] for key in ("club_price", "app_price", "price")
                    if product.get(key) not in (None, "")), None)
    secondary = next((product[key] for key in ("promotion_price", "price")
                      if product.get(key) not in (None, "")), None)
    payload = deepcopy(product)
    if primary is not None:
        payload["price"] = primary
    if not bind_product_to_item_slot(session, slot.id, payload):
        return False

    extras = slot.metadata.get("extra_bindings") or {}
    unit = str(product.get("unit") or "UN").strip().upper().lstrip("/")
    with session.transaction("Aplicar dois precos Limpeza Azul"):
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
            ("club_label", product.get("club_label") or "NO CLUBE"),
        ):
            for node_id in extras.get(role, []):
                node = session.page.node(str(node_id))
                if node is not None and node.kind is NodeKind.TEXT:
                    node.text = str(value)
        snapshot = slot.metadata.setdefault("product_snapshot", {})
        if isinstance(snapshot, dict):
            snapshot["limpeza_club_price"] = "" if primary is None else str(primary)
            snapshot["limpeza_promotion_price"] = "" if secondary is None else str(secondary)
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
