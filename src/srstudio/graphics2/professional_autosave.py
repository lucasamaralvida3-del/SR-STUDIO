from __future__ import annotations

"""Opt-in autosave/recovery controller for the professional G2 editor."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .autosave import AutosaveManager, document_fingerprint
from .operations import GraphicsSession
from .preflight import assert_document_integrity


@dataclass(slots=True, frozen=True)
class AutosaveTickReport:
    saved: bool
    path: str
    document_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RecoveryStatus:
    available: bool
    recoverable: bool
    path: str
    saved_at: str
    size: int
    same_as_live: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RecoveryApplyReport:
    changed: bool
    path: str
    document_id: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProfessionalAutosaveController:
    """Owns recovery points without ever overwriting the explicit project file."""

    def __init__(
        self,
        session: GraphicsSession,
        *,
        root: str | Path | None = None,
        interval_seconds: float = 30.0,
        generations: int = 8,
    ) -> None:
        self.session = session
        self.root = Path(root) if root is not None else (
            Path.home() / ".srstudio5" / "graphics2" / "autosave"
        )
        self.manager = AutosaveManager(
            self.root,
            interval_seconds=interval_seconds,
            generations=generations,
        )

    def tick(self, *, min_interval_seconds: float | None = None) -> AutosaveTickReport:
        path = self.manager.save_if_changed(
            self.session.document,
            min_interval_seconds=min_interval_seconds,
        )
        return AutosaveTickReport(
            saved=path is not None,
            path=str(path or ""),
            document_id=self.session.document.id,
        )

    def status(self) -> RecoveryStatus:
        point = self.manager.latest(self.session.document.id)
        if point is None:
            return RecoveryStatus(False, False, "", "", 0, False)
        try:
            recovered = self.manager.recover(point)
            same = document_fingerprint(recovered) == document_fingerprint(self.session.document)
            return RecoveryStatus(
                available=True,
                recoverable=not same,
                path=str(point.path),
                saved_at=point.saved_at.isoformat(),
                size=point.size,
                same_as_live=same,
            )
        except Exception as exc:
            return RecoveryStatus(
                available=True,
                recoverable=False,
                path=str(point.path),
                saved_at=point.saved_at.isoformat(),
                size=point.size,
                same_as_live=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def recover_latest(self) -> RecoveryApplyReport:
        point = self.manager.latest(self.session.document.id)
        if point is None:
            return RecoveryApplyReport(False, "", self.session.document.id, "Nenhum autosave disponível.")

        recovered = self.manager.recover(point)
        if recovered.id != self.session.document.id:
            return RecoveryApplyReport(
                False,
                str(point.path),
                self.session.document.id,
                "Recovery pertence a outro projeto.",
            )
        assert_document_integrity(recovered)

        if document_fingerprint(recovered) == document_fingerprint(self.session.document):
            self.manager.mark_current_state(self.session.document)
            return RecoveryApplyReport(
                False,
                str(point.path),
                self.session.document.id,
                "O autosave já corresponde ao estado atual.",
            )

        before = self.session.history.capture(self.session.document)
        self.session.document = recovered
        self.session.clear_selection()
        after = self.session.history.capture(self.session.document)
        self.session.history.push("Recuperar autosave", before, after)
        self.manager.mark_current_state(self.session.document)
        return RecoveryApplyReport(
            True,
            str(point.path),
            self.session.document.id,
            "Autosave recuperado. Undo restaura o estado anterior.",
        )

    def clear(self) -> int:
        return self.manager.clear(self.session.document.id)
