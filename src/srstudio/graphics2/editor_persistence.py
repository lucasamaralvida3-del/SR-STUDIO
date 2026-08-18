from __future__ import annotations

"""Estado de persistência do editor G2, independente de Qt/QML.

O host usa este módulo para responder sem heurística de UI:
1. o documento mudou desde o último save confirmado?;
2. o autosave já cobre exatamente o estado atual?;
3. existe um recovery point mais novo que o projeto salvo em disco?;
4. qual recovery pertence à última sessão que realmente ficou pendente?
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
import json
import os

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
        digest = document_or_digest if isinstance(document_or_digest, str) else document_digest(document_or_digest)
        self.autosave_digest = digest
        return digest

    def mark_saved(self, document_or_digest: GraphicsDocument | str, path: str | Path) -> str:
        digest = document_or_digest if isinstance(document_or_digest, str) else document_digest(document_or_digest)
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


@dataclass(slots=True, frozen=True)
class RecoverySession:
    document_id: str
    recovery_path: Path
    source_path: Path | None = None


class EditorRecoveryJournal:
    """Ponteiro atômico para a última sessão com mudanças ainda não salvas.

    Recovery points antigos continuam disponíveis para diagnóstico, mas somente
    este ponteiro pode fazer o Studio retomar automaticamente um projeto ao abrir
    sem arquivo. Isso evita restaurar um autosave histórico já superado por um
    save manual mais novo.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "last-session.json"
        self._lock = RLock()

    def mark(self, document_id: str, recovery_path: str | Path, *, source_path: str | Path | None = None) -> None:
        recovery = Path(recovery_path).resolve()
        source = Path(source_path).resolve() if source_path else None
        payload = {
            "document_id": str(document_id),
            "recovery_path": str(recovery),
            "source_path": str(source) if source else "",
        }
        with self._lock:
            temp = self.path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.path)

    def clear(self, document_id: str | None = None) -> None:
        with self._lock:
            if document_id:
                current = self.current()
                if current is None or current.document_id != str(document_id):
                    return
            self.path.unlink(missing_ok=True)

    def current(self) -> RecoverySession | None:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    return None
                document_id = str(raw.get("document_id") or "")
                recovery_text = str(raw.get("recovery_path") or "")
                source_text = str(raw.get("source_path") or "")
                if not document_id or not recovery_text:
                    return None
                recovery = Path(recovery_text)
                if not recovery.is_file():
                    return None
                source = Path(source_text) if source_text else None
                return RecoverySession(document_id=document_id, recovery_path=recovery, source_path=source)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return None

    def recovery_point(self, manager: AutosaveManager) -> RecoveryPoint | None:
        current = self.current()
        if current is None:
            return None
        for point in manager.list_recovery_points(current.document_id):
            try:
                if point.path.resolve() == current.recovery_path.resolve():
                    return point
            except OSError:
                continue
        return None
