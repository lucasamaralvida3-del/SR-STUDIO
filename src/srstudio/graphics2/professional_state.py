from __future__ import annotations

"""Read-only professional editor state exposed to Qt/QML."""

from dataclasses import asdict, dataclass
from typing import Any

from .inspector_context import inspector_context
from .operations import GraphicsSession
from .usability_gate import inspect_g2_usability


@dataclass(slots=True, frozen=True)
class PageCapabilities:
    page_id: str
    index: int
    count: int
    can_delete: bool
    can_duplicate: bool
    can_move_previous: bool
    can_move_next: bool


@dataclass(slots=True, frozen=True)
class ProfessionalEditorState:
    inspector: dict[str, Any]
    page: PageCapabilities
    usability: dict[str, Any]
    semantic_selection_id: str
    semantic_selection_kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspector": dict(self.inspector),
            "page": asdict(self.page),
            "usability": dict(self.usability),
            "semantic_selection_id": self.semantic_selection_id,
            "semantic_selection_kind": self.semantic_selection_kind,
        }


def build_professional_editor_state(
    session: GraphicsSession,
    *,
    require_multi_product_page: bool = False,
) -> ProfessionalEditorState:
    """Build deterministic read-only state for a focused Studio de Encartes UI."""

    document = session.document
    page = session.page
    page_index = next(
        (index for index, item in enumerate(document.pages) if item.id == page.id),
        0,
    )
    pages = len(document.pages)

    semantic_id, semantic_kind = _semantic_selection(page, session.selection)
    inspector_selection = [semantic_id] if semantic_id else sorted(session.selection)
    context = inspector_context(page, inspector_selection).to_dict()
    usability = inspect_g2_usability(
        document,
        require_multi_product_page=require_multi_product_page,
    ).to_dict()

    return ProfessionalEditorState(
        inspector=context,
        page=PageCapabilities(
            page_id=page.id,
            index=page_index,
            count=pages,
            can_delete=pages > 1,
            can_duplicate=True,
            can_move_previous=page_index > 0,
            can_move_next=page_index < pages - 1,
        ),
        usability=usability,
        semantic_selection_id=semantic_id,
        semantic_selection_kind=semantic_kind,
    )


def _semantic_selection(page, selection: set[str]) -> tuple[str, str]:
    raw = page.metadata.get("semantic_blocks")
    if not selection or not isinstance(raw, dict):
        return "", ""

    candidates: list[tuple[int, str, str]] = []
    selected = set(selection)
    for block_id, block in raw.items():
        if not isinstance(block, dict):
            continue
        members = {str(item) for item in block.get("members") or []}
        if not members or not selected.issubset(members):
            continue
        kind = str(block.get("kind") or "")
        # Prefer the narrowest semantic object. A complete split PriceBlock
        # therefore wins over its enclosing ProductCard when only price tokens
        # are selected.
        candidates.append((len(members), str(block_id), kind))

    if not candidates:
        return "", ""
    _, block_id, kind = min(candidates, key=lambda item: (item[0], item[1]))
    return block_id, kind
