from __future__ import annotations

"""Geometria comercial dos Smart Slots sem alterar os pixels importados.

O ProductCard semântico pode representar um grupo DrawingML maior que o card
comercial real. Este módulo calcula uma geometria de interação separada,
derivada dos bindings do produto e de elementos decorativos exclusivos do card.
Nada aqui move, redimensiona ou remove nodes do documento.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, SmartSlot

SIGNIFICANT_OVERLAP_RATIO = 0.12
_SHARED_DECORATION_OVERLAP = 0.18
_MAX_DECORATION_PAGE_AREA = 0.18
_MAX_DECORATION_EXPANSION = 3.25


@dataclass(slots=True)
class SlotGeometryEntry:
    page_id: str
    slot_id: str
    product_id: str
    label: str
    source_group_id: str
    bound_node_ids: list[str] = field(default_factory=list)
    included_node_ids: list[str] = field(default_factory=list)
    excluded_shared_node_ids: list[str] = field(default_factory=list)
    excluded_large_node_ids: list[str] = field(default_factory=list)
    bounds: dict[str, float] = field(default_factory=dict)
    max_overlap_ratio: float = 0.0
    overlaps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SmartSlotGeometryReport:
    pages: int = 0
    slots: int = 0
    pairs: int = 0
    significant_overlaps: int = 0
    max_overlap_ratio: float = 0.0
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def refresh_smart_slot_geometry(
    document: GraphicsDocument,
    *,
    significant_overlap_ratio: float = SIGNIFICANT_OVERLAP_RATIO,
) -> SmartSlotGeometryReport:
    """Calcula bounds de interação e overlap de todos os Smart Slots.

    Ordem de verdade:
    1. bindings explícitos do slot (imagem/nome/preço/unidade/etc.);
    2. membros visuais exclusivos do ProductCard semântico;
    3. nunca o retângulo do GROUP bruto como bound de interação.

    Os ids dos slots não são alterados e a saída é persistível em metadata.
    """

    report = SmartSlotGeometryReport()
    for page in document.pages:
        report.pages += 1
        entries = _refresh_page(page, significant_overlap_ratio)
        report.slots += len(entries)
        report.entries.extend(entry.to_dict() for entry in entries)
        for entry in entries:
            report.max_overlap_ratio = max(report.max_overlap_ratio, entry.max_overlap_ratio)
        page_report = dict(page.metadata.get("smart_slot_geometry") or {})
        report.pairs += int(page_report.get("pairs") or 0)
        report.significant_overlaps += int(page_report.get("significant_overlaps") or 0)
    document.metadata["smart_slot_geometry"] = report.to_dict()
    document.metadata["smart_slot_geometry_version"] = 1
    return report


def _refresh_page(page: GraphicsPage, significant_overlap_ratio: float) -> list[SlotGeometryEntry]:
    slots = list(page.slots.values())
    if not slots:
        page.metadata["smart_slot_geometry"] = {
            "version": 1,
            "slots": 0,
            "pairs": 0,
            "significant_overlaps": 0,
            "max_overlap_ratio": 0.0,
        }
        return []

    core_ids: dict[str, list[str]] = {slot.id: _binding_node_ids(page, slot) for slot in slots}
    core_bounds: dict[str, Rect | None] = {
        slot.id: _bounds(page, core_ids[slot.id]) for slot in slots
    }

    entries: dict[str, SlotGeometryEntry] = {}
    final_bounds: dict[str, Rect] = {}

    for slot in slots:
        core = core_bounds.get(slot.id)
        ids = list(core_ids.get(slot.id) or [])
        card = _semantic_card(page, slot)
        candidate_ids = _semantic_content_ids(page, card)
        included = list(ids)
        excluded_shared: list[str] = []
        excluded_large: list[str] = []

        if core is None and candidate_ids:
            # Fallback seguro para documentos antigos sem bindings completos:
            # usar conteúdo do card, nunca o GROUP bruto.
            included.extend(node_id for node_id in candidate_ids if node_id not in included)
        elif core is not None:
            for node_id in candidate_ids:
                if node_id in included:
                    continue
                node = page.node(node_id)
                if node is None or node.kind in {NodeKind.GROUP, NodeKind.BACKGROUND}:
                    continue
                if not node.visible or bool(node.metadata.get("fidelity_layer")):
                    continue
                rect = node.rect.normalized()
                if rect.width <= 0 or rect.height <= 0:
                    continue
                page_area = max(page.width * page.height, 1.0)
                if _area(rect) / page_area > _MAX_DECORATION_PAGE_AREA:
                    excluded_large.append(node_id)
                    continue
                if not _commercially_near(rect, core, page):
                    continue
                if _shared_with_other_slot(rect, slot.id, core_bounds):
                    excluded_shared.append(node_id)
                    continue
                proposed = _union_many([core, rect])
                if proposed is None:
                    continue
                if _area(core) > 0 and _area(proposed) / _area(core) > _MAX_DECORATION_EXPANSION:
                    excluded_large.append(node_id)
                    continue
                included.append(node_id)

        final = _bounds(page, included) or core
        if final is None and card is not None:
            raw = card.get("bounds")
            if isinstance(raw, dict):
                final = _rect(raw)
        if final is None:
            final = Rect()

        label = _slot_label(page, slot)
        source_group_id = str((card or {}).get("metadata", {}).get("source_group_id") or slot.metadata.get("source_group_id") or "")
        entry = SlotGeometryEntry(
            page_id=page.id,
            slot_id=slot.id,
            product_id=slot.product_id,
            label=label,
            source_group_id=source_group_id,
            bound_node_ids=list(ids),
            included_node_ids=list(dict.fromkeys(included)),
            excluded_shared_node_ids=excluded_shared,
            excluded_large_node_ids=excluded_large,
            bounds=_rect_dict(final),
        )
        entries[slot.id] = entry
        final_bounds[slot.id] = final

        slot.metadata["effective_bounds"] = _rect_dict(final)
        slot.metadata["effective_node_ids"] = list(entry.included_node_ids)
        slot.metadata["excluded_shared_node_ids"] = list(excluded_shared)
        slot.metadata["excluded_large_node_ids"] = list(excluded_large)
        slot.metadata["geometry_source"] = "bindings+exclusive-card-members"
        slot.metadata["geometry_version"] = 1

    ordered = sorted(
        slots,
        key=lambda slot: (
            round(final_bounds[slot.id].y, 3),
            round(final_bounds[slot.id].x, 3),
            slot.id,
        ),
    )
    for index, slot in enumerate(ordered, start=1):
        slot.metadata["display_index"] = index
        slot.metadata["display_label"] = f"Produto {index}"

    pairs = 0
    significant = 0
    max_ratio = 0.0
    for index, first in enumerate(ordered):
        a = final_bounds[first.id]
        for second in ordered[index + 1 :]:
            b = final_bounds[second.id]
            pairs += 1
            ratio = _slot_overlap_ratio(a, b)
            if ratio <= 0:
                continue
            max_ratio = max(max_ratio, ratio)
            payload_a = {"slot_id": second.id, "slot_overlap_ratio": ratio}
            payload_b = {"slot_id": first.id, "slot_overlap_ratio": ratio}
            entries[first.id].overlaps.append(payload_a)
            entries[second.id].overlaps.append(payload_b)
            entries[first.id].max_overlap_ratio = max(entries[first.id].max_overlap_ratio, ratio)
            entries[second.id].max_overlap_ratio = max(entries[second.id].max_overlap_ratio, ratio)
            if ratio > significant_overlap_ratio:
                significant += 1

    for slot in ordered:
        entry = entries[slot.id]
        slot.metadata["slot_overlap_ratio"] = entry.max_overlap_ratio
        slot.metadata["slot_overlaps"] = list(entry.overlaps)
        slot.metadata["significant_overlap"] = entry.max_overlap_ratio > significant_overlap_ratio

    page.metadata["smart_slot_geometry"] = {
        "version": 1,
        "slots": len(ordered),
        "pairs": pairs,
        "significant_overlaps": significant,
        "max_overlap_ratio": max_ratio,
        "significant_overlap_threshold": significant_overlap_ratio,
        "entries": [entries[slot.id].to_dict() for slot in ordered],
    }
    return [entries[slot.id] for slot in ordered]


def _binding_node_ids(page: GraphicsPage, slot: SmartSlot) -> list[str]:
    ids: list[str] = []
    for node_id in slot.node_by_role.values():
        node_id = str(node_id or "")
        if node_id and node_id in page.nodes and node_id not in ids:
            ids.append(node_id)
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for raw in extras.values():
            if not isinstance(raw, (list, tuple)):
                continue
            for node_id in raw:
                node_id = str(node_id or "")
                if node_id and node_id in page.nodes and node_id not in ids:
                    ids.append(node_id)
    return ids


def _semantic_card(page: GraphicsPage, slot: SmartSlot) -> dict[str, Any] | None:
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    blocks = page.metadata.get("semantic_blocks")
    if not card_id or not isinstance(blocks, dict):
        return None
    card = blocks.get(card_id)
    return card if isinstance(card, dict) else None


def _semantic_content_ids(page: GraphicsPage, card: dict[str, Any] | None) -> list[str]:
    if not card:
        return []
    metadata = card.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    raw = [*(card.get("members") or []), *(metadata.get("content_members") or [])]
    group_id = str(metadata.get("source_group_id") or "")
    if group_id:
        raw.extend(page.descendants(group_id))
    ids: list[str] = []
    for node_id in raw:
        node_id = str(node_id or "")
        if node_id and node_id in page.nodes and node_id not in ids:
            ids.append(node_id)
    return ids


def _slot_label(page: GraphicsPage, slot: SmartSlot) -> str:
    name_id = str(slot.node_by_role.get("name") or "")
    node = page.node(name_id) if name_id else None
    text = " ".join(str(node.text if node is not None else "").replace("\n", " ").split()).strip()
    if text:
        return text
    snapshot = slot.metadata.get("product_snapshot")
    if isinstance(snapshot, dict):
        for key in ("display_name", "name", "original_name"):
            value = str(snapshot.get(key) or "").strip()
            if value:
                return value
    return slot.name or slot.id


def _shared_with_other_slot(rect: Rect, slot_id: str, core_bounds: dict[str, Rect | None]) -> bool:
    for other_id, other in core_bounds.items():
        if other_id == slot_id or other is None:
            continue
        overlap = _intersection_area(rect, other)
        if overlap <= 0:
            continue
        ratio = overlap / max(min(_area(rect), _area(other)), 1.0)
        if ratio >= _SHARED_DECORATION_OVERLAP:
            return True
    return False


def _commercially_near(rect: Rect, core: Rect, page: GraphicsPage) -> bool:
    margin_x = max(core.width * 0.16, page.width * 0.012)
    margin_y = max(core.height * 0.16, page.height * 0.012)
    expanded = Rect(
        core.x - margin_x,
        core.y - margin_y,
        core.width + margin_x * 2.0,
        core.height + margin_y * 2.0,
    )
    if _intersection_area(rect, expanded) > 0:
        return True
    dx = max(expanded.x - rect.right, rect.x - expanded.right, 0.0)
    dy = max(expanded.y - rect.bottom, rect.y - expanded.bottom, 0.0)
    return dx <= page.width * 0.015 and dy <= page.height * 0.015


def _bounds(page: GraphicsPage, node_ids: Iterable[str]) -> Rect | None:
    rects: list[Rect] = []
    for node_id in node_ids:
        node = page.nodes.get(node_id)
        if node is None:
            continue
        # LIMIT/APP e outros bindings opcionais podem permanecer como nodes
        # invisíveis no template. Eles não fazem parte do card que o usuário vê
        # e portanto não podem inflar a área de interação. A IMAGE sintética é
        # exceção: mesmo invisível antes do primeiro produto, ela representa o
        # destino comercial legítimo da foto.
        if not node.visible and not bool(node.metadata.get("semantic_synthetic_image_slot")):
            continue
        rects.append(node.rect.normalized())
    return _union_many(rects)


def _union_many(rects: Iterable[Rect]) -> Rect | None:
    result: Rect | None = None
    for rect in rects:
        rect = rect.normalized()
        if rect.width <= 0 or rect.height <= 0:
            continue
        result = rect if result is None else result.union(rect)
    return result


def _slot_overlap_ratio(a: Rect, b: Rect) -> float:
    overlap = _intersection_area(a, b)
    if overlap <= 0:
        return 0.0
    return overlap / max(min(_area(a), _area(b)), 1.0)


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
    return {
        "x": rect.x,
        "y": rect.y,
        "width": rect.width,
        "height": rect.height,
    }
