from __future__ import annotations

"""Orquestração final da recuperação semântica Canva.

A primeira passagem em ``semantic_placeholders`` pode promover PriceBlocks
órfãos a Smart Slots usando o backplate branco. Como esses novos slots nascem
durante a própria varredura, esta segunda etapa finaliza de forma explícita o
binding IMAGE no mesmo placeholder. Mantê-la separada torna as duas fases
idempotentes e evita mutação recursiva do dicionário de slots.

A etapa também completa somente semântica opcional de alta confiança em cards
recuperados. LIMIT é aceito apenas com assinatura explícita LIMITE+CPF. Um
segundo PriceBlock só vira preço Clube/app quando existe rótulo local CLUBE,
APP ou APLICATIVO próximo. Nenhuma geometria é alterada.
"""

from math import hypot
import re

from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, SmartSlot
from .semantic_blocks import _mark_recovered_editable, semantic_block
from .semantic_placeholders import (
    PlaceholderRecoveryReport,
    _attach_to_semantic_card,
    _ensure_synthetic_image_node,
    _image_box,
    _price_rect,
    recover_canva_image_placeholders,
)

_LIMIT_RE = re.compile(r"(?:\bLIMITE\b.*\bCPF\b|\bCPF\b.*\bLIMITE\b)", re.IGNORECASE)
_APP_LABEL_RE = re.compile(r"\b(?:CLUBE|APP|APLICATIVO)\b", re.IGNORECASE)
_APP_ROLE_MAP = {
    "currency": "app_price_currency",
    "reais": "app_price_integer",
    "cents": "app_price_cents",
    "unit": "app_unit",
    "complete": "app_price_complete",
}


def recover_canva_semantic_cards(document: GraphicsDocument) -> PlaceholderRecoveryReport:
    """Executa recuperação de card + placeholder + IMAGE até estado completo."""

    report = recover_canva_image_placeholders(document)
    recovered_limits = 0
    recovered_app_prices = 0
    for page in document.pages:
        for slot in list(page.slots.values()):
            if not slot.node_by_role.get(BindingRole.IMAGE.value):
                placeholder_id = str(slot.metadata.get("recovered_image_placeholder_id") or "")
                if placeholder_id:
                    placeholder = page.node(placeholder_id)
                    if placeholder is None or placeholder.kind not in {NodeKind.RECT, NodeKind.PATH}:
                        report.warnings.append(
                            f"Smart Slot {slot.id}: placeholder recuperado não existe mais ({placeholder_id})."
                        )
                    else:
                        price_rect = _price_rect(page, slot)
                        if price_rect is None:
                            report.warnings.append(f"Smart Slot {slot.id}: PriceBlock sem geometria para IMAGE sintética.")
                        else:
                            image_rect = _image_box(page, placeholder.rect.normalized(), price_rect)
                            if image_rect is None:
                                report.warnings.append(f"Smart Slot {slot.id}: placeholder não possui área útil de imagem.")
                            else:
                                synthetic = _ensure_synthetic_image_node(page, slot.id, placeholder, image_rect, price_rect)
                                slot.node_by_role[BindingRole.IMAGE.value] = synthetic.id
                                slot.metadata["synthetic_image_node_id"] = synthetic.id
                                slot.metadata["synthetic_image_slot"] = True
                                _attach_to_semantic_card(page, slot, placeholder, synthetic)
                                report.placeholders_matched += 1
                                report.synthetic_image_slots += 1

            if bool(slot.metadata.get("semantic_recovered")):
                limit_added, app_added = _recover_optional_bindings(page, slot)
                recovered_limits += int(limit_added)
                recovered_app_prices += int(app_added)

    document.metadata["semantic_image_placeholders"] = report.to_dict()
    document.metadata["semantic_recovery_complete"] = {
        "ready": not report.warnings,
        "pages": report.pages_scanned,
        "slots": sum(len(page.slots) for page in document.pages),
        "orphan_cards_promoted": report.orphan_cards_promoted,
        "synthetic_image_slots": report.synthetic_image_slots,
        "recovered_limit_bindings": recovered_limits,
        "recovered_app_price_bindings": recovered_app_prices,
        "warnings": list(report.warnings),
    }
    return report


def _recover_optional_bindings(page: GraphicsPage, slot: SmartSlot) -> tuple[bool, bool]:
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    card = semantic_block(page, card_id)
    if not card:
        return False, False

    candidates = _card_candidate_nodes(page, card)
    if not candidates:
        return False, False

    limit_added = _recover_limit_binding(page, slot, card, candidates)
    app_added = _recover_app_price_binding(page, slot, card, candidates)
    return limit_added, app_added


def _recover_limit_binding(
    page: GraphicsPage,
    slot: SmartSlot,
    card: dict,
    candidates: list[GraphicsNode],
) -> bool:
    if slot.node_by_role.get(BindingRole.LIMIT.value):
        return False
    matches = [
        node
        for node in candidates
        if node.kind is NodeKind.TEXT and node.visible and _LIMIT_RE.search(_clean_text(node.text))
    ]
    if len(matches) != 1:
        return False
    node = matches[0]
    slot.node_by_role[BindingRole.LIMIT.value] = node.id
    _mark_recovered_editable(node)
    _attach_card_role(card, BindingRole.LIMIT.value, [node.id])
    node.metadata["semantic_product_card_id"] = str(card.get("id") or "")
    slot.metadata["recovered_limit_binding"] = True
    return True


def _recover_app_price_binding(
    page: GraphicsPage,
    slot: SmartSlot,
    card: dict,
    candidates: list[GraphicsNode],
) -> bool:
    if slot.node_by_role.get(BindingRole.APP_PRICE.value):
        return False
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict) and any(str(role).startswith("app_price_") for role in extras):
        return False

    labels = [
        node
        for node in candidates
        if node.kind is NodeKind.TEXT and node.visible and _APP_LABEL_RE.search(_clean_text(node.text))
    ]
    if not labels:
        return False

    primary_ids = {str(item) for item in slot.metadata.get("semantic_price_block_ids") or [] if item}
    price_ids = [str(item) for item in (card.get("metadata") or {}).get("price_blocks") or [] if item]
    secondary = []
    for block_id in price_ids:
        if block_id in primary_ids:
            continue
        block = semantic_block(page, block_id)
        if not block or str(block.get("kind") or "") != "price_block":
            continue
        roles = dict(block.get("roles") or {})
        if not (roles.get("complete") or (roles.get("reais") and roles.get("cents"))):
            continue
        distance = _nearest_label_distance(page, block, labels, card)
        if distance is not None:
            secondary.append((distance, block_id, block))

    if not secondary:
        return False
    secondary.sort(key=lambda item: (item[0], item[1]))
    # Mais de um preço secundário quase igualmente próximo do rótulo é ambíguo:
    # preservar pixels e não inventar binding é preferível.
    if len(secondary) > 1 and secondary[1][0] - secondary[0][0] < 0.08:
        return False
    distance, block_id, block = secondary[0]
    if distance > 0.72:
        return False

    extras = slot.metadata.setdefault("extra_bindings", {})
    if not isinstance(extras, dict):
        extras = {}
        slot.metadata["extra_bindings"] = extras
    attached = False
    card_roles = card.setdefault("roles", {})
    if not isinstance(card_roles, dict):
        card_roles = {}
        card["roles"] = card_roles

    for canonical, raw_ids in dict(block.get("roles") or {}).items():
        binding = _APP_ROLE_MAP.get(str(canonical))
        if not binding:
            continue
        ids = [str(node_id) for node_id in raw_ids if str(node_id) in page.nodes]
        if not ids:
            continue
        extras[binding] = ids
        card_roles[binding] = list(ids)
        for node_id in ids:
            page.nodes[node_id].metadata["semantic_product_card_id"] = str(card.get("id") or "")
        attached = True

    if not attached:
        return False

    block["slot_id"] = slot.id
    metadata = block.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["smart_slot_id"] = slot.id
        metadata["app_price"] = True
        metadata["recovered_app_price"] = True
    semantic_ids = slot.metadata.setdefault("semantic_price_block_ids", [])
    if isinstance(semantic_ids, list) and block_id not in semantic_ids:
        semantic_ids.append(block_id)
    slot.metadata["recovered_app_price_binding"] = True
    return True


def _card_candidate_nodes(page: GraphicsPage, card: dict) -> list[GraphicsNode]:
    metadata = card.get("metadata") or {}
    ids = {
        str(node_id)
        for node_id in [*(card.get("members") or []), *(metadata.get("content_members") or [])]
        if str(node_id) in page.nodes
    }
    group_id = str(metadata.get("source_group_id") or "")
    if group_id and group_id in page.nodes:
        ids.update(page.descendants(group_id))

    region = metadata.get("region")
    if not isinstance(region, dict):
        region = card.get("bounds") if isinstance(card.get("bounds"), dict) else None
    if isinstance(region, dict):
        rect = _expanded_rect(_rect(region), 0.08)
        for node in page.nodes.values():
            if node.kind is NodeKind.TEXT and node.visible and _intersects(node.rect.normalized(), rect):
                ids.add(node.id)

    return [page.nodes[node_id] for node_id in sorted(ids) if node_id in page.nodes]


def _nearest_label_distance(
    page: GraphicsPage,
    block: dict,
    labels: list[GraphicsNode],
    card: dict,
) -> float | None:
    bounds = block.get("bounds")
    if not isinstance(bounds, dict):
        member_ids = [str(item) for item in block.get("members") or [] if str(item) in page.nodes]
        rect = page.bounds(member_ids)
    else:
        rect = _rect(bounds)
    if rect is None:
        return None
    card_bounds = card.get("bounds")
    card_rect = _rect(card_bounds) if isinstance(card_bounds, dict) else rect
    scale_x = max(card_rect.width, rect.width, 1.0)
    scale_y = max(card_rect.height, rect.height, 1.0)
    best: float | None = None
    for label in labels:
        lr = label.rect.normalized()
        dx = abs(lr.center_x - rect.center_x) / scale_x
        dy = abs(lr.center_y - rect.center_y) / scale_y
        distance = hypot(dx, dy)
        if best is None or distance < best:
            best = distance
    return best


def _attach_card_role(card: dict, role: str, node_ids: list[str]) -> None:
    roles = card.setdefault("roles", {})
    if isinstance(roles, dict):
        roles[str(role)] = list(node_ids)
    metadata = card.setdefault("metadata", {})
    if isinstance(metadata, dict):
        content = metadata.setdefault("content_members", [])
        if isinstance(content, list):
            for node_id in node_ids:
                if node_id not in content:
                    content.append(node_id)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _rect(raw: dict) -> Rect:
    return Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        max(0.0, float(raw.get("width") or 0.0)),
        max(0.0, float(raw.get("height") or 0.0)),
    ).normalized()


def _expanded_rect(rect: Rect, ratio: float) -> Rect:
    dx = rect.width * max(0.0, ratio)
    dy = rect.height * max(0.0, ratio)
    return Rect(rect.x - dx, rect.y - dy, rect.width + dx * 2.0, rect.height + dy * 2.0)


def _intersects(a: Rect, b: Rect) -> bool:
    return not (a.right < b.x or a.x > b.right or a.bottom < b.y or a.y > b.bottom)
