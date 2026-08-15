from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import copy

from .model import GraphicsDocument


@dataclass(slots=True)
class HistoryEntry:
    label: str
    before: dict[str, Any]
    after: dict[str, Any]


class TransactionHistory:
    """Undo/redo por snapshots completos: prioriza correção e reversibilidade."""

    def __init__(self, limit: int = 250) -> None:
        self.limit = max(10, int(limit))
        self._undo: list[HistoryEntry] = []
        self._redo: list[HistoryEntry] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def capture(self, document: GraphicsDocument) -> dict[str, Any]:
        return copy.deepcopy(document.to_dict())

    def push(self, label: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        if before == after:
            return
        self._undo.append(HistoryEntry(label=label, before=copy.deepcopy(before), after=copy.deepcopy(after)))
        if len(self._undo) > self.limit:
            del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()

    def undo(self, current: GraphicsDocument) -> GraphicsDocument:
        if not self._undo:
            return current
        entry = self._undo.pop()
        self._redo.append(entry)
        return GraphicsDocument.from_dict(copy.deepcopy(entry.before))

    def redo(self, current: GraphicsDocument) -> GraphicsDocument:
        if not self._redo:
            return current
        entry = self._redo.pop()
        self._undo.append(entry)
        return GraphicsDocument.from_dict(copy.deepcopy(entry.after))

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
