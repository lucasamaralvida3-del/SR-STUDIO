from __future__ import annotations

"""Recuperação de SmartSlots a partir de nomes semânticos explícitos do PPTX.

Templates profissionais do SR podem nomear caixas como ``SR_PRODUTO``,
``SR_PRECO_PROMO``, ``SR_PRECO_CLUBE``, ``SR_PRECO_ATACADO``,
``SR_QUANTIDADE`` e ``SR_LIMITE``. Esses nomes são evidência mais forte do que
heurística espacial e permitem representar preços e campos comerciais do mesmo
produto em um único SmartSlot.

A recuperação não depende do nome do arquivo, campanha ou offsets fixos. Quando
os marcadores explícitos não existem, o pipeline espacial histórico continua
sendo a única fonte de recuperação.
"""

from hashlib import sha1
from math import hypot
import re
import unicodedata

from .model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, SmartSlot


_CURRENCY_RE = re.compile(r"^R\s*\$$", re.IGNORECASE)


def recover_explicit_named_slots(document: GraphicsDocument) -> int:
    created = 0
    for page in document.pages:
        created += _recover_page(page)
    if created:
        document.metadata["explicit_named_slots"] = {
            "version": 3,
            "created": created,
            "source": "pptx-node-names",
        }
    return created


def _recover_page(page: GraphicsPage) -> int:
    text_nodes = [node for node in page.nodes.values() if node.kind is NodeKind.TEXT and node.visible]
    product_nodes = [node for node in text_nodes if _is_product_name_marker(node)]
    primary_prices = [node for node in text_nodes if _is_primary_price_marker(node)]
    secondary_prices = [node for node in text_nodes if _is_secondary_price_marker(node)]
    wholesale_prices = [node for node in text_nodes if _is_wholesale_price_marker(node)]
    if not product_nodes or not (primary_prices or secondary_prices or wholesale_prices):
        return 0

    primary_units = [node for node in text_nodes if _is_primary_unit_marker(node)]
    secondary_units = [node for node in text_nodes if _is_secondary_unit_marker(node)]
    limit_nodes = [node for node in text_nodes if _is_limit_marker(node)]
    quantity_nodes = [node for node in text_nodes if _is_quantity_marker(node)]
    currencies = [node for node in text_nodes if _CURRENCY_RE.fullmatch(_clean_text(node.text))]
    images = [node for node in page.nodes.values() if node.kind is NodeKind.IMAGE and node.visible]

    used_primary: set[str] = set()
    used_secondary: set[str] = set()
    used_wholesale: set[str] = set()
    used_limits: set[str] = set()
    used_quantities: set[str] = set()
    created = 0
    for product in sorted(product_nodes, key=lambda item: (item.transform.y, item.transform.x, item.id)):
        if _already_bound_as_name(page, product.id):
            continue

        primary = (
            _nearest_node(page, product, primary_prices, used_primary, max_dx=0.48, max_dy=0.48)
            if primary_prices
            else None
        )
        if primary is not None:
            secondary = _nearest_node(page, primary, secondary_prices, used_secondary, max_dx=0.28, max_dy=0.42)
            wholesale = _nearest_node(page, primary, wholesale_prices, used_wholesale, max_dx=0.36, max_dy=0.48)
        else:
            # Club Exclusive e Atacado podem possuir somente um preço
            # especializado. Nesses casos o slot continua pertencendo ao mesmo
            # produto, apenas sem preço base.
            secondary = _nearest_node(page, product, secondary_prices, used_secondary, max_dx=0.52, max_dy=0.58)
            wholesale = _nearest_node(page, product, wholesale_prices, used_wholesale, max_dx=0.52, max_dy=0.58)
        if primary is None and secondary is None and wholesale is None:
            continue

        primary_unit = _nearest_price_companion(page, primary, primary_units) if primary is not None else None
        secondary_unit = (
            _nearest_price_companion(page, secondary, secondary_units)
            if secondary is not None
            else None
        )
        primary_currency = _nearest_price_companion(page, primary, currencies) if primary is not None else None
        excluded_currencies = {primary_currency.id} if primary_currency is not None else set()
        secondary_currency = (
            _nearest_price_companion(
                page,
                secondary,
                currencies,
                exclude=excluded_currencies,
            )
            if secondary is not None
            else None
        )
        if secondary_currency is not None:
            excluded_currencies.add(secondary_currency.id)
        wholesale_currency = (
            _nearest_price_companion(
                page,
                wholesale,
                currencies,
                exclude=excluded_currencies,
            )
            if wholesale is not None
            else None
        )
        limit_node = _nearest_or_unique(
            page,
            product,
            limit_nodes,
            used_limits,
            max_dx=0.60,
            max_dy=0.65,
        )
        quantity_node = _nearest_or_unique(
            page,
            wholesale or primary or product,
            quantity_nodes,
            used_quantities,
            max_dx=0.62,
            max_dy=0.65,
        )
        image = _explicit_product_image(page, product, images)

        node_by_role: dict[str, str] = {"name": product.id}
        if primary is not None:
            node_by_role["price_complete"] = primary.id
            if primary_currency is not None:
                node_by_role["price_currency"] = primary_currency.id
            if primary_unit is not None:
                node_by_role["unit"] = primary_unit.id
        if limit_node is not None:
            node_by_role["limit"] = limit_node.id
        if quantity_node is not None:
            node_by_role["quantity"] = quantity_node.id
        if image is not None:
            node_by_role["image"] = image.id

        extra: dict[str, list[str]] = {}
        if secondary is not None:
            extra["app_price_complete"] = [secondary.id]
            if secondary_currency is not None:
                extra["app_price_currency"] = [secondary_currency.id]
            if secondary_unit is not None:
                extra["app_unit"] = [secondary_unit.id]
        if wholesale is not None:
            extra["wholesale_price"] = [wholesale.id]
            # A caixa de moeda é guardada separadamente para semântica/layout.
            # O runtime comercial decide visibilidade a partir do preço atacado.
            if wholesale_currency is not None:
                extra["wholesale_price_currency"] = [wholesale_currency.id]

        slot_id = _slot_id(page, product)
        slot = SmartSlot(
            id=slot_id,
            name="Produto importado — campos nomeados",
            page_id=page.id,
            node_by_role=node_by_role,
            confidence=0.995,
            metadata={
                "source": "canva-smart-slot",
                "explicit_named_semantics": True,
                "explicit_named_semantics_version": 3,
                "primary_price_node_id": primary.id if primary is not None else "",
                "secondary_price_node_id": secondary.id if secondary is not None else "",
                "wholesale_price_node_id": wholesale.id if wholesale is not None else "",
                "wholesale_currency_node_id": wholesale_currency.id if wholesale_currency is not None else "",
                "quantity_node_id": quantity_node.id if quantity_node is not None else "",
                "limit_node_id": limit_node.id if limit_node is not None else "",
                "extra_bindings": extra,
            },
        )
        page.slots[slot.id] = slot
        if primary is not None:
            used_primary.add(primary.id)
        if secondary is not None:
            used_secondary.add(secondary.id)
        if wholesale is not None:
            used_wholesale.add(wholesale.id)
        if limit_node is not None:
            used_limits.add(limit_node.id)
        if quantity_node is not None:
            used_quantities.add(quantity_node.id)
        created += 1
    return created


def _marker(node: GraphicsNode) -> str:
    raw = str(node.name or node.metadata.get("source_name") or "")
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "_", ascii_text.upper()).strip("_")


def _is_product_name_marker(node: GraphicsNode) -> bool:
    marker = _marker(node)
    return "PRODUTO" in marker and not any(token in marker for token in ("PRECO", "UNIDADE", "IMAGEM", "FOTO"))


def _is_primary_price_marker(node: GraphicsNode) -> bool:
    marker = _marker(node)
    if "PRECO" not in marker:
        return False
    if any(token in marker for token in ("CLUBE", "APP", "APLICATIVO", "ATACADO", "WHOLESALE")):
        return False
    return any(token in marker for token in ("PROMO", "PROMOCAO", "VAREJO", "NORMAL", "SISTEMA", "VENDA")) or marker.endswith("PRECO")


def _is_secondary_price_marker(node: GraphicsNode) -> bool:
    marker = _marker(node)
    return "PRECO" in marker and any(token in marker for token in ("CLUBE", "APP", "APLICATIVO"))


def _is_wholesale_price_marker(node: GraphicsNode) -> bool:
    marker = _marker(node)
    return "PRECO" in marker and any(token in marker for token in ("ATACADO", "WHOLESALE"))


def _is_primary_unit_marker(node: GraphicsNode) -> bool:
    marker = _marker(node)
    if "UNIDADE" not in marker:
        return False
    if any(token in marker for token in ("CLUBE", "APP", "APLICATIVO", "ATACADO", "WHOLESALE")):
        return False
    return any(token in marker for token in ("PROMO", "PROMOCAO", "VAREJO", "NORMAL", "SISTEMA", "VENDA")) or marker.endswith("UNIDADE")


def _is_secondary_unit_marker(node: GraphicsNode) -> bool:
    marker = _marker(node)
    return "UNIDADE" in marker and any(token in marker for token in ("CLUBE", "APP", "APLICATIVO"))


def _is_limit_marker(node: GraphicsNode) -> bool:
    return "LIMITE" in _marker(node)


def _is_quantity_marker(node: GraphicsNode) -> bool:
    marker = _marker(node)
    return any(token in marker for token in ("QUANTIDADE", "QTD", "MINIMO", "MINIMA")) and not any(
        token in marker for token in ("PRODUTO", "PRECO")
    )


def _already_bound_as_name(page: GraphicsPage, node_id: str) -> bool:
    return any(slot.node_by_role.get("name") == node_id for slot in page.slots.values())


def _nearest_or_unique(
    page: GraphicsPage,
    origin: GraphicsNode,
    candidates: list[GraphicsNode],
    used: set[str],
    *,
    max_dx: float,
    max_dy: float,
) -> GraphicsNode | None:
    available = [node for node in candidates if node.id not in used and node.id != origin.id]
    if len(available) == 1:
        return available[0]
    return _nearest_node(page, origin, available, set(), max_dx=max_dx, max_dy=max_dy)


def _nearest_node(
    page: GraphicsPage,
    origin: GraphicsNode,
    candidates: list[GraphicsNode],
    used: set[str],
    *,
    max_dx: float,
    max_dy: float,
) -> GraphicsNode | None:
    ox, oy = origin.rect.center_x, origin.rect.center_y
    best: tuple[float, str, GraphicsNode] | None = None
    for node in candidates:
        if node.id in used or node.id == origin.id:
            continue
        dx = abs(node.rect.center_x - ox) / max(page.width, 1.0)
        dy = abs(node.rect.center_y - oy) / max(page.height, 1.0)
        if dx > max_dx or dy > max_dy:
            continue
        score = hypot(dx, dy)
        candidate = (score, node.id, node)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    return best[2] if best is not None else None


def _nearest_price_companion(
    page: GraphicsPage,
    price: GraphicsNode | None,
    candidates: list[GraphicsNode],
    *,
    exclude: set[str] | None = None,
) -> GraphicsNode | None:
    """Associa moeda/unidade pela distância entre caixas, não entre centros."""

    if price is None:
        return None
    excluded = exclude or set()
    pr = price.rect.normalized()
    max_gap = max(48.0, pr.height * 0.95, min(pr.width * 0.20, page.width * 0.16))
    best: tuple[float, str, GraphicsNode] | None = None
    for node in candidates:
        if node.id in excluded or node.id == price.id:
            continue
        nr = node.rect.normalized()
        dx = max(pr.x - nr.right, nr.x - pr.right, 0.0)
        dy = max(pr.y - nr.bottom, nr.y - pr.bottom, 0.0)
        gap = hypot(dx, dy)
        if gap > max_gap:
            continue
        score = gap + abs(nr.center_y - pr.center_y) * 0.16
        candidate = (score, node.id, node)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    return best[2] if best is not None else None


def _explicit_product_image(
    page: GraphicsPage,
    product: GraphicsNode,
    images: list[GraphicsNode],
) -> GraphicsNode | None:
    """Só vincula imagem quando o próprio PPTX a nomeia como foto do produto."""

    explicit = [
        image
        for image in images
        if "PRODUTO" in _marker(image) and any(token in _marker(image) for token in ("IMAGEM", "FOTO"))
    ]
    if not explicit:
        return None
    return _nearest_node(page, product, explicit, set(), max_dx=0.55, max_dy=0.55)


def _slot_id(page: GraphicsPage, product: GraphicsNode) -> str:
    digest = sha1(f"{page.id}|{product.id}|named-slot-v3".encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"slot:named:{digest}"


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()
