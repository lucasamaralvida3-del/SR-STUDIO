from __future__ import annotations

"""Estado de persistência do editor G2, independente de Qt/QML.

O host usa este módulo para responder três perguntas sem heurística de UI:
1. o documento mudou desde o último save confirmado?;
2. o autosave já cobre exatamente o estado atual?;
3. existe um recovery point mais novo que o projeto salvo em disco?
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json

from .autosave import AutosaveManager, RecoveryPoint
from .model import GraphicsDocument


def document_digest(document: GraphicsDocument) -> str:
    raw = json.dumps(
        document.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()


@dataclass(slots=True)
class EditorPersistenceState:
    """Rastreia save/autosave por conteúdo, não por contadores frágeis de UI."""

    saved_digest: str = ""
    autosave_digest: str = ""
    saved_path: Path | None = None
    recovered_from: RecoveryPoint | None = None

    @classmethod
    def for_document(
        cls,
        document: GraphicsDocument,
        *,
        saved_path: str | Path | None = None,
        already_saved: bool = False,
        recovered_from: RecoveryPoint | None = None,
    ) -> "EditorPersistenceState":
        digest = document_digest(document)
        return cls(
            saved_digest=digest if already_saved and recovered_from is None else "",
            autosave_digest=digest if recovered_from is not None else "",
            saved_path=Path(saved_path).resolve() if saved_path else None,
            recovered_from=recovered_from,
        )

    def is_dirty(self, document: GraphicsDocument) -> bool:
        return document_digest(document) != self.saved_digest

    def needs_autosave(self, document: GraphicsDocument) -> bool:
        digest = document_digest(document)
        return digest != self.saved_digest and digest != self.autosave_digest

    def mark_autosaved(self, document_or_digest: GraphicsDocument | str) -> str:
        digest = (
            document_or_digest
            if isinstance(document_or_digest, str)
            else document_digest(document_or_digest)
        )
        self.autosave_digest = digest
        return digest

    def mark_saved(self, document_or_digest: GraphicsDocument | str, path: str | Path) -> str:
        digest = (
            document_or_digest
            if isinstance(document_or_digest, str)
            else document_digest(document_or_digest)
        )
        self.saved_digest = digest
        self.autosave_digest = digest
        self.saved_path = Path(path).resolve()
        self.recovered_from = None
        return digest


def newer_recovery_point(
    manager: AutosaveManager,
    document: GraphicsDocument,
    saved_path: str | Path | None,
) -> RecoveryPoint | None:
    """Retorna recovery válido somente quando ele é posterior ao save conhecido."""

    point = manager.latest(document.id)
    if point is None:
        return None
    if saved_path is None:
        return point
    path = Path(saved_path)
    try:
        saved_mtime = path.stat().st_mtime
    except OSError:
        return point
    return point if point.saved_at.timestamp() > saved_mtime else None
