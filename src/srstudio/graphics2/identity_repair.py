from __future__ import annotations

"""Repair legacy cross-page identity collisions in SR Scene 2."""

from dataclasses import asdict, dataclass
from typing import Any, TYPE_CHECKING

from .page_clone import clone_page_with_fresh_ids

if TYPE_CHECKING:
    from .operations import GraphicsSession


@dataclass(slots=True, frozen=True)
class RepairedPageIdentity:
    index: int
    original_page_id: str
    repaired_page_id: str
    reason: tuple[str, ...]
    nodes_rekeyed: int
    slots_rekeyed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class IdentityRepairReport:
    changed: bool
    repaired_pages: tuple[RepairedPageIdentity, ...]
    duplicate_page_ids: int
    duplicate_node_ids: int
    duplicate_slot_ids: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "repaired_pages": [item.to_dict() for item in self.repaired_pages],
            "duplicate_page_ids": self.duplicate_page_ids,
            "duplicate_node_ids": self.duplicate_node_ids,
            "duplicate_slot_ids": self.duplicate_slot_ids,
        }


def repair_legacy_identity_collisions(session: "GraphicsSession") -> IdentityRepairReport:
    """Rekey only pages that collide with an earlier page, in one transaction."""
    document = session.document
    seen_pages: set[str] = set()
    seen_nodes: set[str] = set()
    seen_slots: set[str] = set()
    repairs: list[tuple[int, tuple[str, ...], int, int, str]] = []
    dup_pages = dup_nodes = dup_slots = 0

    for index, page in enumerate(document.pages):
        reasons: list[str] = []
        if page.id in seen_pages:
            dup_pages += 1
            reasons.append("duplicate_page_id")
        node_collisions = set(page.nodes).intersection(seen_nodes)
        if node_collisions:
            dup_nodes += len(node_collisions)
            reasons.append("duplicate_node_ids")
        slot_collisions = set(page.slots).intersection(seen_slots)
        if slot_collisions:
            dup_slots += len(slot_collisions)
            reasons.append("duplicate_slot_ids")
        if reasons:
            repairs.append((index, tuple(reasons), len(page.nodes), len(page.slots), page.id))
        else:
            seen_pages.add(page.id)
            seen_nodes.update(page.nodes)
            seen_slots.update(page.slots)

    if not repairs:
        return IdentityRepairReport(False, (), 0, 0, 0)

    records: list[RepairedPageIdentity] = []
    active_id = document.active_page_id
    with session.transaction("Reparar identidades de páginas"):
        for index, reasons, node_count, slot_count, original_id in repairs:
            source = document.pages[index]
            replacement = clone_page_with_fresh_ids(source, name=source.name, rebuild_semantics=True)
            document.pages[index] = replacement
            records.append(
                RepairedPageIdentity(index, original_id, replacement.id, reasons, node_count, slot_count)
            )
        if document.page(active_id) is None:
            replacement_id = next(
                (item.repaired_page_id for item in records if item.original_page_id == active_id),
                document.pages[0].id,
            )
            document.active_page_id = replacement_id

    session.clear_selection()
    return IdentityRepairReport(True, tuple(records), dup_pages, dup_nodes, dup_slots)
