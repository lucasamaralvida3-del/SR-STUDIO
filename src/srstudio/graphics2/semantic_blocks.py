from __future__ import annotations

"""Compostos semânticos de produto e preço para SR Scene 2.

O PPTX/Canva pode armazenar ``R$``, reais, centavos e unidade como caixas de
texto independentes. Visualmente elas formam um único componente. Este módulo
registra essa relação sem destruir a hierarquia OOXML original nem alterar a
geometria importada.

Os compostos ficam em ``page.metadata['semantic_blocks']`` e cada node membro
recebe o id do seu dono semântico. Assim editor, renderer, SR IA e operações
podem tratar o conjunto de forma atômica, mantendo os elementos originais para
fidelidade e round-trip.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, SmartSlot

_PRICE_ROLE_ALIASES: dict[str, str] = {
    BindingRole.CURRENCY.value: "currency",
    "price_currency": "currency",
    BindingRole.PRICE_REAIS.value: "reais",
    "price_integer": "reais",
    BindingRole.PRICE_CENTS.value: "cents",
    "price_cents": "cents",
    BindingRole.UNIT.value: "unit",
    "unit": "unit",
    "price_complete": "complete",
}

_APP_PRICE_ROLE_ALIASES: dict[str, str] = {
    "app_price_currency": "currency",
    "app_price_integer": "reais",
    "app_price_cents": "cents",
    "app_unit": "unit",
    "app_price_complete": "complete",
    BindingRole.APP_PRICE.value: "complete",
}

_PRODUCT_ROLE_NAMES = {
    BindingRole.NAME.value,
    BindingRole.IMAGE.value,
    BindingRole.LIMIT.value,
    BindingRole.APP_PRICE.value,
    BindingRole.WHOLESALE_PRICE.value,
    BindingRole.RETAIL_PRICE.value,
    BindingRole.QUANTITY.value,
    "name",
    "image",
    "limit",
    "app_price_complete",
    "app_price_currency",
    "app_price_integer",
    "app_price_cents",
    "app_unit",
}


@dataclass(slots=True)
class SemanticBlock:
    id: str
    kind: str
    slot_id: str
    members: list[str] = field(default_factory=list)
    roles: dict[str, list[str]] = field(default_factory=dict)
    bounds: dict[str, float] = field(default_factory=dict)
    template_geometry: dict[str, dict[str, float]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SemanticBlockReport:
    price_blocks: int = 0
    app_price_blocks: int = 0
    product_cards: int = 0
    protected_price_nodes: int = 0
    incomplete_price_blocks: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_semantic_blocks(document: GraphicsDocument) -> SemanticBlockReport:
    """Constrói PriceBlock/ProductCard para todos os Smart Slots do documento.

    A função é idempotente e nunca muda x/y/w/h nem parent/children dos nodes.
    Isso é essencial porque ``pptx_groups`` já reconstrói a hierarquia real do
    arquivo fonte e os compostos semânticos são uma camada ortogonal.
    """

    report = SemanticBlockReport()
    for page in document.pages:
        page_blocks: dict[str, dict[str, Any]] = {}
        for slot in page.slots.values():
            bindings = _slot_bindings(slot)
            primary = _build_price_block(page, slot, bindings, _PRICE_ROLE_ALIASES, suffix="price")
            app = _build_price_block(page, slot, bindings, _APP_PRICE_ROLE_ALIASES, suffix="app-price")
            price_ids: list[str] = []
            if primary is not None:
                page_blocks[primary.id] = primary.to_dict()
                price_ids.append(primary.id)
                report.price_blocks += 1
                report.protected_price_nodes += len(primary.members)
                if not bool(primary.metadata.get("complete")):
                    report.incomplete_price_blocks += 1
            if app is not None:
                page_blocks[app.id] = app.to_dict()
                price_ids.append(app.id)
                report.app_price_blocks += 1
                report.protected_price_nodes += len(app.members)
            card = _build_product_card(page, slot, bindings, price_ids)
            if card is not None:
                page_blocks[card.id] = card.to_dict()
                report.product_cards += 1
        page.metadata["semantic_blocks"] = page_blocks
        page.metadata["semantic_blocks_version"] = 1

    document.metadata["semantic_blocks"] = report.to_dict()
    document.metadata["semantic_blocks_version"] = 1
    return report


def semantic_block(page: GraphicsPage, block_id: str) -> dict[str, Any] | None:
    raw = page.metadata.get("semantic_blocks")
    if not isinstance(raw, dict):
        return None
    item = raw.get(str(block_id))
    return item if isinstance(item, dict) else None


def semantic_owner(page: GraphicsPage, node_id: str, *, prefer_card: bool = True) -> str:
    node = page.node(node_id)
    if node is None:
        return ""
    if prefer_card:
        owner = str(node.metadata.get("semantic_product_card_id") or "")
        if owner:
            return owner
    return str(node.metadata.get("semantic_price_block_id") or "")


def semantic_member_ids(page: GraphicsPage, block_id: str) -> list[str]:
    block = semantic_block(page, block_id)
    if not block:
        return []
    return [str(node_id) for node_id in block.get("members") or [] if str(node_id) in page.nodes]


def _slot_bindings(slot: SmartSlot) -> dict[str, list[str]]:
    bindings: dict[str, list[str]] = {}
    for role, node_id in slot.node_by_role.items():
        if node_id:
            bindings.setdefault(str(role), []).append(str(node_id))
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for role, node_ids in extras.items():
            if isinstance(node_ids, (list, tuple)):
                for node_id in node_ids:
                    if node_id:
                        bindings.setdefault(str(role), []).append(str(node_id))
    return bindings


def _build_price_block(
    page: GraphicsPage,
    slot: SmartSlot,
    bindings: dict[str, list[str]],
    aliases: dict[str, str],
    *,
    suffix: str,
) -> SemanticBlock | None:
    roles: dict[str, list[str]] = {}
    for raw_role, node_ids in bindings.items():
        canonical = aliases.get(raw_role)
        if not canonical:
            continue
        valid = [node_id for node_id in node_ids if node_id in page.nodes]
        if valid:
            roles.setdefault(canonical, []).extend(valid)
    members = _unique(node_id for ids in roles.values() for node_id in ids)
    if not members:
        return None
    block_id = f"priceblock:{slot.id}:{suffix}"
    bounds = _bounds_dict(page, members)
    geometry = {node_id: _geometry(page.nodes[node_id], bounds) for node_id in members}
    split_complete = all(roles.get(key) for key in ("currency", "reais", "cents", "unit"))
    complete = split_complete or bool(roles.get("complete"))
    for canonical, ids in roles.items():
        for node_id in ids:
            node = page.nodes[node_id]
            node.metadata["semantic_price_block_id"] = block_id
            node.metadata["semantic_price_role"] = canonical
            if node.kind is NodeKind.TEXT:
                # NoWrap não é auto-fit. O renderer só deve reduzir um token de
                # preço quando ele realmente exceder a caixa de origem.
                node.style["nowrap"] = True
                node.style["semantic_fit_policy"] = "overflow_only"
                node.style["semantic_price_role"] = canonical
                node.style["semantic_price_block_id"] = block_id
    return SemanticBlock(
        id=block_id,
        kind="price_block",
        slot_id=slot.id,
        members=members,
        roles=roles,
        bounds=bounds,
        template_geometry=geometry,
        metadata={
            "complete": complete,
            "split_complete": split_complete,
            "atomic": True,
            "preserve_source_geometry": True,
            "source": str(slot.metadata.get("source") or "smart-slot"),
        },
    )


def _build_product_card(
    page: GraphicsPage,
    slot: SmartSlot,
    bindings: dict[str, list[str]],
    price_block_ids: list[str],
) -> SemanticBlock | None:
    members: list[str] = []
    roles: dict[str, list[str]] = {}
    for raw_role, node_ids in bindings.items():
        valid = [node_id for node_id in node_ids if node_id in page.nodes]
        if not valid:
            continue
        if raw_role in _PRODUCT_ROLE_NAMES or raw_role in _PRICE_ROLE_ALIASES or raw_role in _APP_PRICE_ROLE_ALIASES:
            roles.setdefault(raw_role, []).extend(valid)
            members.extend(valid)
    members = _unique(members)
    if not members:
        return None
    block_id = f"productcard:{slot.id}"
    bounds = _bounds_dict(page, members)
    geometry = {node_id: _geometry(page.nodes[node_id], bounds) for node_id in members}
    for node_id in members:
        page.nodes[node_id].metadata["semantic_product_card_id"] = block_id
    slot.metadata["semantic_product_card_id"] = block_id
    slot.metadata["semantic_price_block_ids"] = list(price_block_ids)
    return SemanticBlock(
        id=block_id,
        kind="product_card",
        slot_id=slot.id,
        members=members,
        roles=roles,
        bounds=bounds,
        template_geometry=geometry,
        metadata={
            "price_blocks": list(price_block_ids),
            "atomic": True,
            "preserve_source_geometry": True,
            "source": str(slot.metadata.get("source") or "smart-slot"),
        },
    )


def _bounds_dict(page: GraphicsPage, members: list[str]) -> dict[str, float]:
    rect: Rect | None = None
    for node_id in members:
        node = page.node(node_id)
        if node is None:
            continue
        rect = node.rect if rect is None else rect.union(node.rect)
    if rect is None:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _geometry(node: GraphicsNode, bounds: dict[str, float]) -> dict[str, float]:
    width = max(float(bounds.get("width") or 0.0), 1e-9)
    height = max(float(bounds.get("height") or 0.0), 1e-9)
    return {
        "x": node.transform.x,
        "y": node.transform.y,
        "width": node.transform.width,
        "height": node.transform.height,
        "rotation": node.transform.rotation,
        "relative_x": (node.transform.x - float(bounds.get("x") or 0.0)) / width,
        "relative_y": (node.transform.y - float(bounds.get("y") or 0.0)) / height,
        "relative_width": node.transform.width / width,
        "relative_height": node.transform.height / height,
    }


def _unique(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
