from __future__ import annotations

"""Conservative multi-product SmartSlot planning for real flyer pages."""

from dataclasses import asdict, dataclass
from typing import Any, Sequence, TYPE_CHECKING

from .import_bridge import CanvaBindingService

if TYPE_CHECKING:
    from .operations import GraphicsSession


@dataclass(slots=True, frozen=True)
class SlotFillAssignment:
    slot_id: str
    product_index: int
    product_id: str
    slot_confidence: float
    expected_current_product_id: str


@dataclass(slots=True, frozen=True)
class SlotFillSkip:
    slot_id: str
    reason: str
    confidence: float


@dataclass(slots=True, frozen=True)
class SlotFillPlan:
    page_id: str
    assignments: tuple[SlotFillAssignment, ...]
    skipped_slots: tuple[SlotFillSkip, ...]
    unassigned_product_indexes: tuple[int, ...]
    overwrite: bool
    min_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "assignments": [asdict(item) for item in self.assignments],
            "skipped_slots": [asdict(item) for item in self.skipped_slots],
            "unassigned_product_indexes": list(self.unassigned_product_indexes),
            "overwrite": self.overwrite,
            "min_confidence": self.min_confidence,
        }


@dataclass(slots=True, frozen=True)
class SlotFillApplyReport:
    applied: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]

    @property
    def changed(self) -> bool:
        return bool(self.applied)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": list(self.applied),
            "rejected": [{"slot_id": slot_id, "reason": reason} for slot_id, reason in self.rejected],
            "changed": self.changed,
        }


def plan_smart_slot_fill(
    session: "GraphicsSession",
    products: Sequence[dict[str, Any]],
    *,
    overwrite: bool = False,
    min_confidence: float = 0.72,
) -> SlotFillPlan:
    """Plan visual-order slot population without changing the flyer.

    Low-confidence, locked and already-populated slots are skipped by default.
    Products are never guessed by name here: this planner only maps an explicit
    ordered product list to slots considered safe enough for automatic filling.
    """

    page = session.page
    threshold = max(0.0, min(1.0, float(min_confidence)))
    ordered_slots = sorted(page.slots.values(), key=lambda slot: _slot_sort_key(session, slot))
    eligible = []
    skipped: list[SlotFillSkip] = []

    for slot in ordered_slots:
        confidence = max(0.0, min(1.0, float(slot.confidence)))
        if slot.locked:
            skipped.append(SlotFillSkip(slot.id, "locked", confidence))
            continue
        if confidence < threshold:
            skipped.append(SlotFillSkip(slot.id, "low_confidence", confidence))
            continue
        if slot.product_id and not overwrite:
            skipped.append(SlotFillSkip(slot.id, "already_populated", confidence))
            continue
        eligible.append(slot)

    assignments: list[SlotFillAssignment] = []
    product_indexes = [index for index, product in enumerate(products) if isinstance(product, dict)]
    for slot, product_index in zip(eligible, product_indexes):
        product = products[product_index]
        assignments.append(
            SlotFillAssignment(
                slot_id=slot.id,
                product_index=product_index,
                product_id=str(product.get("id") or product.get("product_id") or ""),
                slot_confidence=max(0.0, min(1.0, float(slot.confidence))),
                expected_current_product_id=str(slot.product_id or ""),
            )
        )

    assigned_indexes = {item.product_index for item in assignments}
    unassigned = tuple(index for index in product_indexes if index not in assigned_indexes)
    return SlotFillPlan(
        page_id=page.id,
        assignments=tuple(assignments),
        skipped_slots=tuple(skipped),
        unassigned_product_indexes=unassigned,
        overwrite=bool(overwrite),
        min_confidence=threshold,
    )


def apply_slot_fill_plan(
    session: "GraphicsSession",
    plan: SlotFillPlan,
    products: Sequence[dict[str, Any]],
) -> SlotFillApplyReport:
    """Apply a previously reviewed plan while rejecting stale slot state.

    Existing binding services keep their proven per-card transactions. That
    means a rare failed card cannot corrupt cards already applied, and each
    successful card remains individually undoable.
    """

    if session.page.id != plan.page_id:
        return SlotFillApplyReport((), (("", "active_page_changed"),))

    applied: list[str] = []
    rejected: list[tuple[str, str]] = []
    for assignment in plan.assignments:
        slot = session.page.slots.get(assignment.slot_id)
        if slot is None:
            rejected.append((assignment.slot_id, "slot_missing"))
            continue
        if slot.locked:
            rejected.append((assignment.slot_id, "slot_locked"))
            continue
        if str(slot.product_id or "") != assignment.expected_current_product_id:
            rejected.append((assignment.slot_id, "slot_state_changed"))
            continue
        if assignment.product_index < 0 or assignment.product_index >= len(products):
            rejected.append((assignment.slot_id, "product_missing"))
            continue
        product = products[assignment.product_index]
        if not isinstance(product, dict):
            rejected.append((assignment.slot_id, "product_invalid"))
            continue
        current_product_id = str(product.get("id") or product.get("product_id") or "")
        if assignment.product_id and current_product_id != assignment.product_id:
            rejected.append((assignment.slot_id, "product_state_changed"))
            continue

        if slot.metadata.get("source") == "canva-smart-slot":
            changed = CanvaBindingService.bind(session, slot.id, dict(product))
        else:
            session.bind_product(slot.id, dict(product))
            changed = True
        if changed:
            applied.append(slot.id)
        else:
            rejected.append((slot.id, "binding_rejected"))

    return SlotFillApplyReport(tuple(applied), tuple(rejected))


def _slot_sort_key(session: "GraphicsSession", slot) -> tuple[float, float, str]:
    rects = []
    for node_id in slot.node_by_role.values():
        node = session.page.node(node_id)
        if node is not None:
            rects.append(node.rect)
    if not rects:
        return (float("inf"), float("inf"), slot.id)
    return (
        round(min(rect.y for rect in rects), 3),
        round(min(rect.x for rect in rects), 3),
        slot.id,
    )
