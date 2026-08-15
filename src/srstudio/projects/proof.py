from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from srstudio.core.models import StudioProject


@dataclass(slots=True)
class PageApproval:
    page_id: str
    approved: bool = False
    approved_at: str = ""
    reviewer: str = ""
    note: str = ""


@dataclass(slots=True)
class ProofState:
    approvals: dict[str, PageApproval] = field(default_factory=dict)


class ProofManager:
    """Controla prova/aprovação por página sem alterar o conteúdo da arte."""

    def __init__(self, project: StudioProject) -> None:
        self.project = project
        self.state = ProofState()
        self._restore()

    def approve(self, page_id: str, reviewer: str = "", note: str = "") -> PageApproval:
        if not any(page.id == page_id for page in self.project.pages):
            raise KeyError(page_id)
        item = PageApproval(page_id, True, datetime.now(timezone.utc).isoformat(), reviewer, note)
        self.state.approvals[page_id] = item
        self._persist()
        return item

    def reject(self, page_id: str, reviewer: str = "", note: str = "") -> PageApproval:
        item = PageApproval(page_id, False, "", reviewer, note)
        self.state.approvals[page_id] = item
        self._persist()
        return item

    def reset_page(self, page_id: str) -> None:
        self.state.approvals.pop(page_id, None)
        self._persist()

    def all_approved(self) -> bool:
        page_ids = {page.id for page in self.project.pages}
        return bool(page_ids) and all(self.state.approvals.get(page_id, PageApproval(page_id)).approved for page_id in page_ids)

    def pending_pages(self) -> list[str]:
        return [page.id for page in self.project.pages if not self.state.approvals.get(page.id, PageApproval(page.id)).approved]

    def _persist(self) -> None:
        self.project.settings["proof"] = {
            page_id: {
                "approved": item.approved,
                "approved_at": item.approved_at,
                "reviewer": item.reviewer,
                "note": item.note,
            }
            for page_id, item in self.state.approvals.items()
        }

    def _restore(self) -> None:
        raw = self.project.settings.get("proof", {})
        if not isinstance(raw, dict):
            return
        for page_id, data in raw.items():
            if isinstance(data, dict):
                self.state.approvals[page_id] = PageApproval(page_id=page_id, **data)
