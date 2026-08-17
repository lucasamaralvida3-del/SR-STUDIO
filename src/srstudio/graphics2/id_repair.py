from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import GraphicsDocument, GraphicsPage
from .page_clone import clone_page_with_fresh_ids


@dataclass(slots=True)
class IdRepairReport:
    changed: bool = False
    pages_rebuilt: int = 0
    repairs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "pages_rebuilt": self.pages_rebuilt,
            "repairs": [dict(item) for item in self.repairs],
        }


def repair_legacy_cross_page_ids(document: GraphicsDocument) -> IdRepairReport:
    """Repara somente colisões globais herdadas de duplicação de página antiga.

    Builds anteriores à correção de clone multipágina podiam copiar uma página
    inteira por ``deepcopy`` e trocar apenas ``page.id``. Isso deixava IDs de
    nós, SmartSlots e SemanticBlocks iguais em páginas diferentes. O editor
    atual exige IDs globais únicos; em vez de tornar um projeto antigo
    impossível de editar, reconstruímos apenas a página conflitante com o clone
    canônico de IDs frescos. Layout, assets e conteúdo continuam iguais.

    A migração é idempotente e registrada em metadata para nunca ser silenciosa.
    """

    report = IdRepairReport()
    seen_page_ids: set[str] = set()
    seen_node_ids: set[str] = set()
    seen_slot_ids: set[str] = set()
    seen_block_ids: set[str] = set()

    for index in range(len(document.pages)):
        page = document.pages[index]
        reasons = _collision_reasons(
            page,
            seen_page_ids=seen_page_ids,
            seen_node_ids=seen_node_ids,
            seen_slot_ids=seen_slot_ids,
            seen_block_ids=seen_block_ids,
        )
        if reasons:
            old_page_id = page.id
            old_active_was_unambiguous = (
                document.active_page_id == old_page_id and old_page_id not in seen_page_ids
            )
            rebuilt = clone_page_with_fresh_ids(page, name=page.name)
            document.pages[index] = rebuilt
            page = rebuilt
            if old_active_was_unambiguous:
                document.active_page_id = rebuilt.id
            report.changed = True
            report.pages_rebuilt += 1
            report.repairs.append(
                {
                    "page_index": index,
                    "page_name": page.name,
                    "old_page_id": old_page_id,
                    "new_page_id": page.id,
                    "reasons": reasons,
                }
            )

        seen_page_ids.add(page.id)
        seen_node_ids.update(page.nodes)
        seen_slot_ids.update(page.slots)
        seen_block_ids.update(_semantic_block_ids(page))

    if report.changed:
        history = document.metadata.setdefault("g2_integrity_migrations", [])
        if not isinstance(history, list):
            history = []
            document.metadata["g2_integrity_migrations"] = history
        history.append(
            {
                "kind": "legacy-cross-page-id-repair",
                "pages_rebuilt": report.pages_rebuilt,
                "repairs": [dict(item) for item in report.repairs],
            }
        )
        document.metadata["g2_integrity_repair_last"] = report.to_dict()
    return report


def _collision_reasons(
    page: GraphicsPage,
    *,
    seen_page_ids: set[str],
    seen_node_ids: set[str],
    seen_slot_ids: set[str],
    seen_block_ids: set[str],
) -> list[str]:
    reasons: list[str] = []
    if page.id in seen_page_ids:
        reasons.append("duplicate_page_id")
    if seen_node_ids.intersection(page.nodes):
        reasons.append("duplicate_node_id")
    if seen_slot_ids.intersection(page.slots):
        reasons.append("duplicate_slot_id")
    if seen_block_ids.intersection(_semantic_block_ids(page)):
        reasons.append("duplicate_semantic_id")
    return reasons


def _semantic_block_ids(page: GraphicsPage) -> set[str]:
    raw = page.metadata.get("semantic_blocks")
    if not isinstance(raw, dict):
        return set()
    return {str(block_id) for block_id in raw}
