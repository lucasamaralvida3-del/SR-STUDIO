from __future__ import annotations

"""Consolidação sistêmica de falsos Smart Slots decorativos.

A detecção semântica do PPTX/Canva pode produzir candidatos intermediários a
ProductCard em torno de PriceBlocks, grupos ou placeholders. Esta passagem
final separa entidade de produto de artwork decorativo sem mover/remover nodes.

Regra central: um shape/backplate não é produto. Slots fracos, sem identidade
independente, que estejam contidos em um slot de produto mais forte são
incorporados como membros visuais do card real e o slot falso é removido.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, SmartSlot

_CONTAINMENT_RATIO = 0.72
_STRONGER_EVIDENCE_MARGIN = 18.0
_DECORATIVE_KINDS = {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.PATH, NodeKind.LINE}
_PRICE_ROLES = {
    BindingRole.CURRENCY.value,
    BindingRole.PRICE_REAIS.value,
    BindingRole.PRICE_CENTS.value,
    BindingRole.RETAIL_PRICE.value,
    BindingRole.WHOLESALE_PRICE.value,
    BindingRole.UNIT.value,
    "price_amount_complete",
    "price_complete",
    "app_price_complete",
    "app_price_currency",
    "app_price_integer",
    "app_price_cents",
    "app_unit",
}


@dataclass(slots=True)
class SlotEvidence:
    slot_id: str
    score: float = 0.0
    explicit_identity: bool = False
    has_real_image: bool = False
    has_synthetic_image: bool = False
    has_name: bool = False
    has_price: bool = False
    group_composition: bool = False
    role_count: int = 0
    positive_product_entity: bool = False
    bound_node_ids: list[str] = field(default_factory=list)
    card_member_ids: list[str] = field(default_factory=list)
    bounds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PageSlotDetectionMetrics:
    page_id: str
    expected_product_candidates: int = 0
    smart_slots_before: int = 0
    decorative_false_positives_before: int = 0
    smart_slots_after: int = 0
    false_positives_after: int = 0
    merged_decorative_members: int = 0
    orphan_slots: int = 0
    dropped_slot_ids: list[str] = field(default_factory=list)
    merged_slots: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SmartSlotDetectionReport:
    pages: int = 0
    smart_slots_before: int = 0
    decorative_false_positives_before: int = 0
    smart_slots_after: int = 0
    false_positives_after: int = 0
    merged_decorative_members: int = 0
    orphan_slots: int = 0
    page_metrics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def consolidate_smart_slot_false_positives(document: GraphicsDocument) -> SmartSlotDetectionReport:
    """Remove somente candidatos falsos, preservando integralmente o artwork.

    A função atua depois da inferência semântica. Nenhum node é apagado, movido
    ou redimensionado. Quando existe um card real mais forte, os membros visuais
    do candidato falso passam a integrar o ProductCard real.
    """

    report = SmartSlotDetectionReport()
    for page in document.pages:
        metrics = _consolidate_page(page)
        report.pages += 1
        report.smart_slots_before += metrics.smart_slots_before
        report.decorative_false_positives_before += metrics.decorative_false_positives_before
        report.smart_slots_after += metrics.smart_slots_after
        report.false_positives_after += metrics.false_positives_after
        report.merged_decorative_members += metrics.merged_decorative_members
        report.orphan_slots += metrics.orphan_slots
        report.page_metrics.append(metrics.to_dict())
    document.metadata["smart_slot_detection"] = report.to_dict()
    document.metadata["smart_slot_detection_version"] = 1
    return report


def merge_decorative_slot_into(page: GraphicsPage, source: SmartSlot, target: SmartSlot) -> int:
    """Anexa members visuais de ``source`` ao card de ``target`` e remove source.

    É usado tanto pela deduplicação automática quanto pela ação manual futura.
    Nodes continuam na mesma posição/z-order e no mesmo parent DrawingML.
    """

    if source.id == target.id:
        return 0
    blocks = page.metadata.get("semantic_blocks")
    blocks = blocks if isinstance(blocks, dict) else {}
    source_card_id = str(source.metadata.get("semantic_product_card_id") or "")
    target_card_id = str(target.metadata.get("semantic_product_card_id") or "")
    source_card = blocks.get(source_card_id) if source_card_id else None
    target_card = blocks.get(target_card_id) if target_card_id else None
    source_members = _card_member_ids(page, source, source_card if isinstance(source_card, dict) else None)
    target_bounds = _slot_bounds(page, target)

    added: list[str] = []
    if isinstance(target_card, dict):
        metadata = target_card.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            target_card["metadata"] = metadata
        content = metadata.setdefault("content_members", [])
        if not isinstance(content, list):
            content = []
            metadata["content_members"] = content
        for node_id in source_members:
            node = page.node(node_id)
            if node is None:
                continue
            # O false slot pode carregar textos do PriceBlock, mas a associação
            # visual deve aceitar somente o que pertence espacialmente ao card.
            if target_bounds is not None and _intersection_area(node.rect.normalized(), target_bounds) <= 0:
                continue
            if node_id not in content:
                content.append(node_id)
                added.append(node_id)
            node.metadata["semantic_product_card_visual_id"] = target_card_id
            node.metadata["decorative_card_member"] = True

    if isinstance(source_card, dict):
        source_card["slot_id"] = ""
        metadata = source_card.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["decorative_false_positive"] = True
            metadata["classification"] = "decorative/card_member"
            metadata["merged_into_slot_id"] = target.id
            metadata["merged_into_product_card_id"] = target_card_id
            metadata.pop("smart_slot_id", None)

    _detach_slot_from_price_blocks(page, source)
    page.slots.pop(source.id, None)
    return len(added)


def drop_non_product_slot(page: GraphicsPage, slot: SmartSlot, *, reason: str = "decorative-false-positive") -> None:
    """Remove a entidade Smart Slot sem alterar qualquer node visual."""

    blocks = page.metadata.get("semantic_blocks")
    blocks = blocks if isinstance(blocks, dict) else {}
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    card = blocks.get(card_id) if card_id else None
    if isinstance(card, dict):
        card["slot_id"] = ""
        metadata = card.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["decorative_false_positive"] = True
            metadata["classification"] = "decorative/non-product"
            metadata["drop_reason"] = reason
            metadata.pop("smart_slot_id", None)
    for node_id in _card_member_ids(page, slot, card if isinstance(card, dict) else None):
        node = page.node(node_id)
        if node is not None:
            node.metadata["semantic_non_product"] = True
            node.metadata["decorative_card_member"] = True
    _detach_slot_from_price_blocks(page, slot)
    page.slots.pop(slot.id, None)


def slot_evidence(page: GraphicsPage, slot: SmartSlot) -> SlotEvidence:
    blocks = page.metadata.get("semantic_blocks")
    blocks = blocks if isinstance(blocks, dict) else {}
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    card = blocks.get(card_id) if card_id else None
    card = card if isinstance(card, dict) else None
    node_ids = _binding_node_ids(page, slot)
    members = _card_member_ids(page, slot, card)

    explicit = _has_explicit_identity(page, slot, node_ids)
    image_id = str(slot.node_by_role.get(BindingRole.IMAGE.value) or "")
    image = page.node(image_id) if image_id else None
    synthetic = bool(image and image.metadata.get("semantic_synthetic_image_slot"))
    real_image = bool(image and image.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND} and not synthetic)
    name_id = str(slot.node_by_role.get(BindingRole.NAME.value) or "")
    name = page.node(name_id) if name_id else None
    has_name = bool(name and name.kind is NodeKind.TEXT and _clean_text(name.text))
    roles = set(str(role) for role in slot.node_by_role)
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        roles.update(str(role) for role in extras)
    has_price = bool(roles & _PRICE_ROLES)
    group_id = str((card or {}).get("metadata", {}).get("source_group_id") or slot.metadata.get("source_group_id") or "")
    group_composition = bool(group_id and has_price and (has_name or real_image))

    score = 0.0
    if explicit:
        score += 100.0
    if real_image:
        score += 42.0
    if synthetic:
        score += 5.0
    if has_name:
        score += 22.0
    if has_price:
        score += 22.0
    if group_composition:
        score += 16.0
    score += min(12.0, float(len(roles)) * 2.0)

    positive = bool(
        explicit
        or (real_image and (has_name or has_price))
        or (has_name and has_price and len(roles) >= 3)
        or group_composition
    )
    bounds = _slot_bounds(page, slot)
    return SlotEvidence(
        slot_id=slot.id,
        score=score,
        explicit_identity=explicit,
        has_real_image=real_image,
        has_synthetic_image=synthetic,
        has_name=has_name,
        has_price=has_price,
        group_composition=group_composition,
        role_count=len(roles),
        positive_product_entity=positive,
        bound_node_ids=node_ids,
        card_member_ids=members,
        bounds=_rect_dict(bounds) if bounds is not None else {},
    )


def _consolidate_page(page: GraphicsPage) -> PageSlotDetectionMetrics:
    metrics = PageSlotDetectionMetrics(page_id=page.id)
    slots = list(page.slots.values())
    metrics.smart_slots_before = len(slots)
    if not slots:
        return metrics

    evidence = {slot.id: slot_evidence(page, slot) for slot in slots}
    metrics.evidence = [evidence[slot.id].to_dict() for slot in slots]
    bounds = {slot.id: _slot_bounds(page, slot) for slot in slots}

    false_candidates: list[tuple[SmartSlot, SmartSlot | None]] = []
    for slot in slots:
        ev = evidence[slot.id]
        parent = _best_stronger_container(slot, slots, evidence, bounds)
        nested_duplicate = bool(
            parent is not None
            and not ev.explicit_identity
            and not ev.has_real_image
            and evidence[parent.id].score >= ev.score + _STRONGER_EVIDENCE_MARGIN
        )
        weak_orphan = not ev.positive_product_entity
        if nested_duplicate or weak_orphan:
            false_candidates.append((slot, parent))

    metrics.decorative_false_positives_before = len(false_candidates)
    false_ids = {slot.id for slot, _ in false_candidates}
    metrics.expected_product_candidates = max(0, len(slots) - len(false_ids))

    for slot, parent in false_candidates:
        if slot.id not in page.slots:
            continue
        if parent is not None and parent.id in page.slots:
            added = merge_decorative_slot_into(page, slot, parent)
            metrics.merged_decorative_members += added
            metrics.merged_slots.append({"source_slot_id": slot.id, "target_slot_id": parent.id, "members": added})
            metrics.dropped_slot_ids.append(slot.id)
        else:
            drop_non_product_slot(page, slot)
            metrics.dropped_slot_ids.append(slot.id)

    metrics.smart_slots_after = len(page.slots)
    after_evidence = [slot_evidence(page, slot) for slot in page.slots.values()]
    metrics.false_positives_after = sum(1 for item in after_evidence if not item.positive_product_entity)
    metrics.orphan_slots = metrics.false_positives_after
    return metrics


def _best_stronger_container(
    slot: SmartSlot,
    slots: list[SmartSlot],
    evidence: dict[str, SlotEvidence],
    bounds: dict[str, Rect | None],
) -> SmartSlot | None:
    source = bounds.get(slot.id)
    if source is None or _area(source) <= 0:
        return None
    candidates: list[tuple[float, float, SmartSlot]] = []
    for other in slots:
        if other.id == slot.id:
            continue
        target = bounds.get(other.id)
        if target is None or _area(target) <= 0:
            continue
        if evidence[other.id].score <= evidence[slot.id].score:
            continue
        containment = _intersection_area(source, target) / max(_area(source), 1.0)
        if containment < _CONTAINMENT_RATIO:
            continue
        candidates.append((-containment, -evidence[other.id].score, other))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2].id))
    return candidates[0][2]


def _has_explicit_identity(page: GraphicsPage, slot: SmartSlot, node_ids: list[str]) -> bool:
    if not bool(slot.metadata.get("semantic_recovered")):
        source = str(slot.metadata.get("source") or "").strip().lower()
        if source not in {"", "canva-smart-slot"}:
            return True
    for node_id in node_ids:
        node = page.node(node_id)
        if node is None:
            continue
        slot_id = str(node.metadata.get("slot_id") or "")
        slot_role = str(node.metadata.get("slot_role") or "")
        if slot_id and slot_id == slot.id:
            return True
        if slot_role and not bool(node.metadata.get("semantic_synthetic_image_slot")):
            return True
    return False


def _detach_slot_from_price_blocks(page: GraphicsPage, slot: SmartSlot) -> None:
    blocks = page.metadata.get("semantic_blocks")
    if not isinstance(blocks, dict):
        return
    ids = [str(item) for item in slot.metadata.get("semantic_price_block_ids") or [] if item]
    for block_id in ids:
        block = blocks.get(block_id)
        if not isinstance(block, dict):
            continue
        block["slot_id"] = ""
        metadata = block.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.pop("smart_slot_id", None)
            metadata["decorative_parent_slot_removed"] = slot.id


def _binding_node_ids(page: GraphicsPage, slot: SmartSlot) -> list[str]:
    result: list[str] = []
    for node_id in slot.node_by_role.values():
        value = str(node_id or "")
        if value and value in page.nodes and value not in result:
            result.append(value)
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for raw in extras.values():
            values = raw if isinstance(raw, (list, tuple, set)) else [raw]
            for node_id in values:
                value = str(node_id or "")
                if value and value in page.nodes and value not in result:
                    result.append(value)
    return result


def _card_member_ids(page: GraphicsPage, slot: SmartSlot, card: dict[str, Any] | None) -> list[str]:
    result = list(_binding_node_ids(page, slot))
    if card:
        metadata = card.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        raw: list[Any] = [*(card.get("members") or []), *(metadata.get("content_members") or [])]
        group_id = str(metadata.get("source_group_id") or "")
        if group_id and group_id in page.nodes:
            raw.extend(page.descendants(group_id))
        for node_id in raw:
            value = str(node_id or "")
            if value and value in page.nodes and value not in result:
                result.append(value)
    return result


def _slot_bounds(page: GraphicsPage, slot: SmartSlot) -> Rect | None:
    manual = slot.metadata.get("user_adjusted_bounds") if slot.metadata.get("adjustment_source") == "manual" else None
    if isinstance(manual, dict):
        rect = _rect(manual)
        if _area(rect) > 0:
            return rect
    effective = slot.metadata.get("effective_bounds")
    if isinstance(effective, dict):
        rect = _rect(effective)
        if _area(rect) > 0:
            return rect
    ids = _binding_node_ids(page, slot)
    rects = [page.nodes[node_id].rect.normalized() for node_id in ids if page.nodes[node_id].visible or page.nodes[node_id].metadata.get("semantic_synthetic_image_slot")]
    return _union_many(rects)


def _union_many(rects: Iterable[Rect]) -> Rect | None:
    result: Rect | None = None
    for rect in rects:
        value = rect.normalized()
        if _area(value) <= 0:
            continue
        result = value if result is None else result.union(value)
    return result


def _intersection_area(a: Rect, b: Rect) -> float:
    a, b = a.normalized(), b.normalized()
    width = max(0.0, min(a.right, b.right) - max(a.x, b.x))
    height = max(0.0, min(a.bottom, b.bottom) - max(a.y, b.y))
    return width * height


def _area(rect: Rect) -> float:
    rect = rect.normalized()
    return max(0.0, rect.width) * max(0.0, rect.height)


def _rect(raw: dict[str, Any]) -> Rect:
    return Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        max(0.0, float(raw.get("width") or 0.0)),
        max(0.0, float(raw.get("height") or 0.0)),
    ).normalized()


def _rect_dict(rect: Rect) -> dict[str, float]:
    rect = rect.normalized()
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()
