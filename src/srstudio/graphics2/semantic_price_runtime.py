from __future__ import annotations

"""Recuperação complementar de preços completos em PPTX reais do G2.

O recuperador histórico cobre o padrão Canva fracionado em quatro caixas:
``R$`` + ``92`` + ``,77`` + ``KG``. Templates SR/PowerPoint também usam um
padrão igualmente válido, porém diferente: ``R$`` + ``92,77`` + ``CADA``.

No baseline oficial integrado, ``semantic_blocks`` v8 também reconhece valores
completos. Esta camada coopera com esse caminho: preserva nodes já pertencentes
a SmartSlots (inclusive bindings extras/comerciais), enriquece blocos completos
nativos com unidade quando ela existe e só então recupera preços ainda soltos.
"""

from math import hypot
import re
from typing import Any, Callable

from .model import GraphicsNode, GraphicsPage, NodeKind


_COMPLETE_PRICE_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{3})*|\d{1,6})[,.]\d{2}$")
_COMMERCIAL_UNIT_RE = re.compile(
    r"^/?(?:KG|UN|UND|UNID|UNIDADE|G|L|ML|LT|CX|PCT|PC|BDJ|CADA)$",
    re.IGNORECASE,
)
_RESERVED_SENTINEL = "__sr_slot_bound_price_reserved__"


def install_complete_price_recovery_guard(semantic_module: Any) -> None:
    """Acrescenta preço completo sem competir com slots explícitos ou v8."""

    if bool(getattr(semantic_module, "_sr_complete_price_recovery_installed", False)):
        return

    original: Callable[[GraphicsPage], list[Any]] = semantic_module._recover_unbound_price_blocks

    def guarded_recovery(page: GraphicsPage) -> list[Any]:
        # ``semantic_blocks`` v8 reserva apenas nodes já marcados como membros de
        # PriceBlock. Bindings comerciais extras (por exemplo atacado) ainda não
        # receberam essa marca quando a recuperação espacial roda. Reserve-os
        # temporariamente para que a semântica explícita tenha precedência.
        temporary = _reserve_slot_bound_nodes(page)
        try:
            recovered = list(original(page))
        finally:
            _restore_reserved_nodes(page, temporary)

        recovered = _enrich_native_complete_blocks(page, semantic_module, recovered)
        recovered.extend(_recover_complete_price_blocks(page, semantic_module, recovered))
        return recovered

    guarded_recovery.__name__ = original.__name__
    guarded_recovery.__doc__ = original.__doc__
    guarded_recovery.__module__ = original.__module__
    semantic_module._sr_split_price_recovery_original = original
    semantic_module._recover_unbound_price_blocks = guarded_recovery
    semantic_module._sr_complete_price_recovery_installed = True


def _reserve_slot_bound_nodes(page: GraphicsPage) -> list[str]:
    bound_ids: set[str] = set()
    for slot in page.slots.values():
        bound_ids.update(str(node_id) for node_id in slot.node_by_role.values() if node_id)
        extras = slot.metadata.get("extra_bindings")
        if isinstance(extras, dict):
            for raw_ids in extras.values():
                if isinstance(raw_ids, str):
                    if raw_ids:
                        bound_ids.add(raw_ids)
                elif isinstance(raw_ids, (list, tuple, set)):
                    bound_ids.update(str(node_id) for node_id in raw_ids if node_id)

    temporary: list[str] = []
    for node_id in bound_ids:
        node = page.nodes.get(node_id)
        if node is None or node.metadata.get("semantic_price_block_id"):
            continue
        node.metadata["semantic_price_block_id"] = _RESERVED_SENTINEL
        temporary.append(node_id)
    return temporary


def _restore_reserved_nodes(page: GraphicsPage, temporary: list[str]) -> None:
    for node_id in temporary:
        node = page.nodes.get(node_id)
        if node is not None and node.metadata.get("semantic_price_block_id") == _RESERVED_SENTINEL:
            node.metadata.pop("semantic_price_block_id", None)


def _enrich_native_complete_blocks(page: GraphicsPage, semantic_module: Any, existing: list[Any]) -> list[Any]:
    """Anexa unidade a blocos completos criados nativamente pelo semantic v8."""

    text_nodes = [node for node in page.nodes.values() if node.kind is NodeKind.TEXT and node.visible]
    used = {str(node_id) for block in existing for node_id in getattr(block, "members", [])}
    units = [
        node
        for node in text_nodes
        if node.id not in used and _COMMERCIAL_UNIT_RE.fullmatch(semantic_module._clean_text(node.text))
    ]
    if not units:
        return existing

    output: list[Any] = []
    for block in existing:
        roles = {str(role): list(node_ids) for role, node_ids in getattr(block, "roles", {}).items()}
        complete_ids = roles.get("complete") or []
        if not complete_ids or roles.get("unit"):
            output.append(block)
            continue
        price = page.nodes.get(str(complete_ids[0]))
        if price is None:
            output.append(block)
            continue
        unit = _nearest_cluster_token(page, price, units, used, role="unit")
        if unit is None:
            output.append(block)
            continue

        roles["unit"] = [unit.id]
        source = str(getattr(block, "metadata", {}).get("source") or "complete-price-spatial-recovery")
        recovered_flag = bool(getattr(block, "metadata", {}).get("recovered", True))
        rebuilt = semantic_module._make_price_block(
            page,
            str(getattr(block, "id", "")),
            str(getattr(block, "slot_id", "")),
            roles,
            source=source,
            recovered=recovered_flag,
        )
        rebuilt.metadata.update(dict(getattr(block, "metadata", {}) or {}))
        rebuilt.metadata["complete_price_token"] = True
        rebuilt.metadata["commercial_unit"] = semantic_module._clean_text(unit.text)
        output.append(rebuilt)
        used.add(unit.id)
    return output


def _recover_complete_price_blocks(page: GraphicsPage, semantic_module: Any, existing: list[Any]) -> list[Any]:
    text_nodes = [node for node in page.nodes.values() if node.kind is NodeKind.TEXT and node.visible]
    reserved = {
        str(node_id)
        for block in existing
        for node_id in getattr(block, "members", [])
    }
    reserved.update(
        node.id
        for node in text_nodes
        if node.metadata.get("semantic_price_block_id")
    )

    clean = semantic_module._clean_text
    currencies = [
        node
        for node in text_nodes
        if node.id not in reserved and semantic_module._CURRENCY_RE.fullmatch(clean(node.text))
    ]
    prices = [
        node
        for node in text_nodes
        if node.id not in reserved and _COMPLETE_PRICE_RE.fullmatch(clean(node.text))
    ]
    units = [
        node
        for node in text_nodes
        if node.id not in reserved and _COMMERCIAL_UNIT_RE.fullmatch(clean(node.text))
    ]

    output: list[Any] = []
    prices.sort(key=lambda node: (node.transform.y, node.transform.x, node.id))
    for price in prices:
        if price.id in reserved:
            continue
        currency = _nearest_cluster_token(page, price, currencies, reserved, role="currency")
        unit = _nearest_cluster_token(page, price, units, reserved, role="unit")
        if currency is None or unit is None:
            continue

        members = [currency.id, price.id, unit.id]
        if len(set(members)) != 3:
            continue
        stable = semantic_module._stable_node_key(price)
        block = semantic_module._make_price_block(
            page,
            f"priceblock:recovered:{stable}",
            "",
            {"currency": [currency.id], "complete": [price.id], "unit": [unit.id]},
            source="complete-price-spatial-recovery",
            recovered=True,
        )
        block.metadata["complete_price_token"] = True
        block.metadata["price_text"] = clean(price.text)
        block.metadata["commercial_unit"] = clean(unit.text)
        output.append(block)
        reserved.update(members)
    return output


def _nearest_cluster_token(
    page: GraphicsPage,
    price: GraphicsNode,
    candidates: list[GraphicsNode],
    reserved: set[str],
    *,
    role: str,
) -> GraphicsNode | None:
    pr = price.rect.normalized()
    max_gap = max(48.0, pr.height * 0.9, min(pr.width * 0.18, page.width * 0.14))
    best: tuple[float, float, str, GraphicsNode] | None = None
    for node in candidates:
        if node.id in reserved:
            continue
        nr = node.rect.normalized()
        gap = _rect_gap(pr, nr)
        if gap > max_gap:
            continue

        vertical_delta = abs(nr.center_y - pr.center_y)
        if role == "currency" and nr.center_y > pr.bottom + pr.height * 0.35:
            continue
        if role == "unit" and nr.center_y < pr.y - pr.height * 0.35:
            continue
        score = gap + vertical_delta * 0.18
        tie = abs(nr.center_x - pr.center_x)
        candidate = (score, tie, node.id, node)
        if best is None or candidate[:3] < best[:3]:
            best = candidate
    return best[3] if best is not None else None


def _rect_gap(a: Any, b: Any) -> float:
    dx = max(a.x - b.right, b.x - a.right, 0.0)
    dy = max(a.y - b.bottom, b.y - a.bottom, 0.0)
    return hypot(dx, dy)
