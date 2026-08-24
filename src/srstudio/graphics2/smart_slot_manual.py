from __future__ import annotations

"""Edição manual persistente da área semântica dos Smart Slots.

Somente metadata do SmartSlot/documento é alterado. Nenhum node visual é
movido, redimensionado ou removido. As correções ficam disponíveis como corpus
estruturado para futura melhoria do detector, sem treinamento online.
"""

from datetime import datetime, timezone
from typing import Any

from .model import GraphicsDocument, GraphicsPage, Rect, SmartSlot
from .operations import GraphicsSession
from .smart_slot_detection import drop_non_product_slot, merge_decorative_slot_into

_MANUAL_VERSION = 1
_FEEDBACK_SCHEMA = "srstudio/smart-slot-feedback-1"


def set_manual_slot_bounds(
    session: GraphicsSession,
    slot_id: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
) -> dict[str, float]:
    page = session.page
    slot = _require_slot(page, slot_id)
    rect = _validated_rect(page, Rect(float(x), float(y), float(width), float(height)))
    before = _effective_bounds(slot)
    original = _original_bounds(slot) or before
    if original is None:
        original = rect

    with session.transaction("Ajustar Smart Slot"):
        slot.metadata.setdefault("original_detected_bounds", _rect_dict(original))
        slot.metadata["user_adjusted_bounds"] = _rect_dict(rect)
        slot.metadata["effective_bounds"] = _rect_dict(rect)
        slot.metadata["adjustment_source"] = "manual"
        slot.metadata["manual_adjustment_version"] = _MANUAL_VERSION
        slot.metadata["manual_adjustment_at"] = _timestamp()
        slot.metadata["geometry_source"] = "manual"
        # Overlap and drop-target invalidation are intentionally commit-on-release.
        # No node scan or semantic rebuild is required while the pointer is moving.
        overlap_ids = _slot_overlap_ids(page, slot, rect)
        slot.metadata["manual_overlap_slot_ids"] = overlap_ids
        slot.metadata["manual_overlap_count"] = len(overlap_ids)
        page.metadata["drop_target_revision"] = int(page.metadata.get("drop_target_revision") or 0) + 1
        _record_feedback(
            session.document,
            page,
            slot,
            action="manual-bounds",
            auto_bounds=original,
            user_bounds=rect,
            false_positive=False,
        )
    return _rect_dict(rect)


def restore_auto_slot_bounds(session: GraphicsSession, slot_id: str) -> dict[str, float]:
    page = session.page
    slot = _require_slot(page, slot_id)
    original = _original_bounds(slot)
    if original is None:
        raise ValueError("Smart Slot não possui original_detected_bounds para restaurar.")
    with session.transaction("Restaurar detecção automática do Smart Slot"):
        slot.metadata.pop("user_adjusted_bounds", None)
        slot.metadata["effective_bounds"] = _rect_dict(original)
        slot.metadata["adjustment_source"] = "auto-restored"
        slot.metadata["manual_adjustment_version"] = _MANUAL_VERSION
        slot.metadata["manual_adjustment_at"] = _timestamp()
        slot.metadata["geometry_source"] = "original-detected-bounds"
        _record_feedback(
            session.document,
            page,
            slot,
            action="restore-auto",
            auto_bounds=original,
            user_bounds=original,
            false_positive=False,
        )
    return _rect_dict(original)


def mark_slot_non_product(session: GraphicsSession, slot_id: str, *, reason: str = "manual-non-product") -> None:
    page = session.page
    slot = _require_slot(page, slot_id)
    auto = _original_bounds(slot) or _effective_bounds(slot)
    user = _effective_bounds(slot)
    with session.transaction("Marcar Smart Slot como não-produto"):
        _record_feedback(
            session.document,
            page,
            slot,
            action="manual-slot-delete",
            auto_bounds=auto,
            user_bounds=user,
            false_positive=True,
            manual_slot_delete=True,
        )
        _remember_suppressed_slot(session.document, page, slot, reason=reason)
        drop_non_product_slot(page, slot, reason=reason)


def merge_slot_manually(session: GraphicsSession, source_slot_id: str, target_slot_id: str) -> int:
    page = session.page
    source = _require_slot(page, source_slot_id)
    target = _require_slot(page, target_slot_id)
    if source.id == target.id:
        raise ValueError("Smart Slot de origem e destino são iguais.")
    auto = _original_bounds(source) or _effective_bounds(source)
    user = _effective_bounds(source)
    with session.transaction("Associar Smart Slot decorativo ao produto"):
        _record_feedback(
            session.document,
            page,
            source,
            action="manual-slot-merge",
            auto_bounds=auto,
            user_bounds=user,
            false_positive=True,
            manual_slot_merge=target.id,
        )
        merged = merge_decorative_slot_into(page, source, target)
    return merged


def snap_bounds_to_grid(
    bounds: dict[str, float],
    *,
    spacing: float,
    enabled: bool,
    page: GraphicsPage | None = None,
) -> dict[str, float]:
    rect = Rect(
        float(bounds.get("x") or 0.0),
        float(bounds.get("y") or 0.0),
        float(bounds.get("width") or 0.0),
        float(bounds.get("height") or 0.0),
    ).normalized()
    if enabled and spacing > 0:
        step = max(0.1, float(spacing))
        left = round(rect.x / step) * step
        top = round(rect.y / step) * step
        right = round(rect.right / step) * step
        bottom = round(rect.bottom / step) * step
        rect = Rect(left, top, max(step, right - left), max(step, bottom - top))
    if page is not None:
        rect = _validated_rect(page, rect)
    return _rect_dict(rect)


def _record_feedback(
    document: GraphicsDocument,
    page: GraphicsPage,
    slot: SmartSlot,
    *,
    action: str,
    auto_bounds: Rect | None,
    user_bounds: Rect | None,
    false_positive: bool,
    manual_slot_merge: str = "",
    manual_slot_delete: bool = False,
) -> None:
    auto_nodes = _nodes_inside(page, auto_bounds) if auto_bounds is not None else []
    user_nodes = _nodes_inside(page, user_bounds) if user_bounds is not None else []
    auto_set = set(auto_nodes)
    user_set = set(user_nodes)
    entry = {
        "schema": _FEEDBACK_SCHEMA,
        "action": action,
        "recorded_at": _timestamp(),
        "version": _MANUAL_VERSION,
        "slot_id": slot.id,
        "page_id": page.id,
        "source_pptx_fingerprint": str(document.metadata.get("import_fingerprint_sha256") or ""),
        "auto_bounds": _rect_dict(auto_bounds) if auto_bounds is not None else {},
        "user_bounds": _rect_dict(user_bounds) if user_bounds is not None else {},
        "nodes_inside_auto": auto_nodes,
        "nodes_inside_user": user_nodes,
        "nodes_removed": sorted(auto_set - user_set),
        "nodes_added": sorted(user_set - auto_set),
        "false_positive": bool(false_positive),
        "manual_slot_merge": str(manual_slot_merge or ""),
        "manual_slot_delete": bool(manual_slot_delete),
        "layout_features": _slot_features(page, slot),
    }
    feedback = document.metadata.setdefault("smart_slot_feedback", [])
    if not isinstance(feedback, list):
        feedback = []
        document.metadata["smart_slot_feedback"] = feedback
    feedback.append(entry)
    document.metadata["smart_slot_feedback_version"] = _MANUAL_VERSION


def _remember_suppressed_slot(document: GraphicsDocument, page: GraphicsPage, slot: SmartSlot, *, reason: str) -> None:
    items = document.metadata.setdefault("suppressed_smart_slots", [])
    if not isinstance(items, list):
        items = []
        document.metadata["suppressed_smart_slots"] = items
    items.append(
        {
            "slot_id": slot.id,
            "page_id": page.id,
            "source_pptx_fingerprint": str(document.metadata.get("import_fingerprint_sha256") or ""),
            "reason": reason,
            "recorded_at": _timestamp(),
        }
    )


def _slot_features(page: GraphicsPage, slot: SmartSlot) -> dict[str, Any]:
    roles = sorted(str(role) for role in slot.node_by_role)
    kinds: dict[str, int] = {}
    for node_id in _slot_node_ids(slot):
        node = page.node(node_id)
        if node is None:
            continue
        key = node.kind.value
        kinds[key] = kinds.get(key, 0) + 1
    return {
        "roles": roles,
        "node_kinds": kinds,
        "confidence": float(slot.confidence),
        "source": str(slot.metadata.get("source") or ""),
        "source_group_id": str(slot.metadata.get("source_group_id") or ""),
        "semantic_product_card_id": str(slot.metadata.get("semantic_product_card_id") or ""),
    }


def _nodes_inside(page: GraphicsPage, bounds: Rect) -> list[str]:
    area = max(bounds.width * bounds.height, 1.0)
    result: list[str] = []
    for node in page.nodes.values():
        rect = node.rect.normalized()
        overlap = _intersection_area(bounds, rect)
        if overlap <= 0:
            continue
        node_area = max(rect.width * rect.height, 1.0)
        # Captura nodes semanticamente dentro da área, sem exigir contenção total
        # de text boxes que podem ultrapassar alguns pixels no Canva.
        if overlap / min(area, node_area) >= 0.18:
            result.append(node.id)
    return sorted(result)


def _slot_node_ids(slot: SmartSlot) -> list[str]:
    result: list[str] = []
    for node_id in slot.node_by_role.values():
        value = str(node_id or "")
        if value and value not in result:
            result.append(value)
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for raw in extras.values():
            values = raw if isinstance(raw, (list, tuple, set)) else [raw]
            for node_id in values:
                value = str(node_id or "")
                if value and value not in result:
                    result.append(value)
    return result


def _require_slot(page: GraphicsPage, slot_id: str) -> SmartSlot:
    slot = page.slots.get(str(slot_id))
    if slot is None:
        raise KeyError(f"Smart Slot inexistente: {slot_id}")
    return slot


def _original_bounds(slot: SmartSlot) -> Rect | None:
    raw = slot.metadata.get("original_detected_bounds")
    return _rect_from_metadata(raw)


def _effective_bounds(slot: SmartSlot) -> Rect | None:
    raw = slot.metadata.get("effective_bounds")
    return _rect_from_metadata(raw)


def _rect_from_metadata(raw: object) -> Rect | None:
    if not isinstance(raw, dict):
        return None
    rect = Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        float(raw.get("width") or 0.0),
        float(raw.get("height") or 0.0),
    ).normalized()
    return rect if rect.width > 0 and rect.height > 0 else None


def _validated_rect(page: GraphicsPage, rect: Rect) -> Rect:
    rect = rect.normalized()
    width = max(1.0, min(rect.width, max(page.width, 1.0)))
    height = max(1.0, min(rect.height, max(page.height, 1.0)))
    x = min(max(0.0, rect.x), max(0.0, page.width - width))
    y = min(max(0.0, rect.y), max(0.0, page.height - height))
    return Rect(x, y, width, height)


def _slot_overlap_ids(page: GraphicsPage, slot: SmartSlot, bounds: Rect) -> list[str]:
    result: list[str] = []
    for other in page.slots.values():
        if other.id == slot.id:
            continue
        other_bounds = _effective_bounds(other) or _original_bounds(other)
        if other_bounds is None:
            continue
        if _intersection_area(bounds, other_bounds) > 0:
            result.append(other.id)
    return sorted(result)


def _intersection_area(a: Rect, b: Rect) -> float:
    a, b = a.normalized(), b.normalized()
    width = max(0.0, min(a.right, b.right) - max(a.x, b.x))
    height = max(0.0, min(a.bottom, b.bottom) - max(a.y, b.y))
    return width * height


def _rect_dict(rect: Rect) -> dict[str, float]:
    rect = rect.normalized()
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
