from __future__ import annotations

"""Estado de persistência do editor G2, independente de Qt/QML.

O host usa este módulo para responder sem heurística de UI:
1. o documento mudou desde o último save confirmado?;
2. o autosave já cobre exatamente o estado atual?;
3. existe um recovery point mais novo que o projeto salvo em disco?;
4. qual recovery pertence à última sessão que realmente ficou pendente?;
5. qual foi o último projeto `.srscene` salvo/aberto para continuar o trabalho?
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
    """Digest semântico estável entre pacote e cache de runtime.

    Extração de assets/fontes altera caminhos locais e flags de transporte para
    que Qt/QML consiga abrir recursos do ZIP. Essas mutações não são edição do
    projeto e não podem tornar o documento dirty nem invalidar a relação entre
    um autosave e o save manual em que ele se baseou.
    """

    raw = json.dumps(
        _persistence_payload(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _persistence_payload(document: GraphicsDocument) -> dict[str, object]:
    payload = document.to_dict()

    assets = payload.get("assets")
    if isinstance(assets, dict):
        for asset in assets.values():
            if not isinstance(asset, dict):
                continue
            # Com hash de conteúdo, source/embedded são apenas a forma de
            # transporte (arquivo original, membro ZIP ou cache extraído).
            if str(asset.get("sha256") or ""):
                asset["source"] = "<content-addressed>"
                asset["embedded"] = False

    pages = payload.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            nodes = page.get("nodes")
            if not isinstance(nodes, dict):
                continue
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                metadata = node.get("metadata")
                if isinstance(metadata, dict):
                    metadata.pop("bound_image_source", None)
                    metadata.pop("package_asset_extracted", None)

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        fonts = metadata.get("embedded_fonts")
        if isinstance(fonts, list):
            for font in fonts:
                if not isinstance(font, dict) or not str(font.get("sha256") or ""):
                    continue
                font.pop("extracted_path", None)
                font.pop("embedded", None)

    return payload


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
    """Compatibilidade para journals antigos que ainda dependiam de mtime."""

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
    # None = journal legado sem esta informação; "" = autosave criado antes do
    # primeiro save manual; hash = digest semântico do save-base confirmado.
    base_saved_digest: str | None = None


class EditorRecoveryJournal:
    """Ponteiro atômico para a última sessão com mudanças ainda não salvas."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "last-session.json"
        self._lock = RLock()

    def mark(
        self,
        document_id: str,
        recovery_path: str | Path,
        *,
        source_path: str | Path | None = None,
        base_saved_digest: str | None = None,
    ) -> None:
        recovery = Path(recovery_path).resolve()
        source = Path(source_path).resolve() if source_path else None
        payload: dict[str, object] = {
            "document_id": str(document_id),
            "recovery_path": str(recovery),
            "source_path": str(source) if source else "",
        }
        if base_saved_digest is not None:
            payload["base_saved_digest"] = str(base_saved_digest)
        with self._lock:
            current = self.current()
            if (
                current is not None
                and current.document_id == str(document_id)
                and current.recovery_path.resolve() != recovery
                and _recovery_generation_key(current.recovery_path) > _recovery_generation_key(recovery)
            ):
                # Saves/autosaves são serializados pelo AutosaveManager, mas
                # threads diferentes ainda podem retomar após o I/O em ordem
                # inversa. Nunca deixe um callback tardio regredir o journal.
                return
            _atomic_json(self.path, payload)

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
                base_saved_digest = (
                    str(raw.get("base_saved_digest") or "")
                    if "base_saved_digest" in raw
                    else None
                )
                return RecoverySession(
                    document_id=document_id,
                    recovery_path=recovery,
                    source_path=source,
                    base_saved_digest=base_saved_digest,
                )
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


@dataclass(slots=True, frozen=True)
class RecentProject:
    document_id: str
    path: Path


class EditorRecentProject:
    """Ponteiro separado para o último `.srscene` salvo/aberto com sucesso.

    Recovery e projeto recente têm semânticas diferentes: recovery ganha sempre
    quando há alterações pendentes; se não houver recovery, o Studio pode abrir
    o último projeto salvo para cumprir o fluxo diário "fechar → abrir → continuar".
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "last-project.json"
        self._lock = RLock()

    def mark(self, project_path: str | Path, *, document_id: str) -> None:
        project = Path(project_path).resolve()
        if project.suffix.lower() not in {".srscene", ".zip"}:
            return
        payload = {"document_id": str(document_id), "path": str(project)}
        with self._lock:
            _atomic_json(self.path, payload)

    def current(self) -> RecentProject | None:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    return None
                document_id = str(raw.get("document_id") or "")
                project_text = str(raw.get("path") or "")
                if not document_id or not project_text:
                    return None
                project = Path(project_text)
                if not project.is_file() or project.suffix.lower() not in {".srscene", ".zip"}:
                    return None
                return RecentProject(document_id=document_id, path=project)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                return None

    def clear(self, document_id: str | None = None) -> None:
        with self._lock:
            if document_id:
                current = self.current()
                if current is None or current.document_id != str(document_id):
                    return
            self.path.unlink(missing_ok=True)


def _recovery_generation_key(path: Path) -> tuple[int, str]:
    try:
        return path.stat().st_mtime_ns, path.name
    except OSError:
        return 0, path.name


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
