from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
import json
import os

from .model import GraphicsDocument
from .package import load_package, save_package


@dataclass(slots=True, frozen=True)
class RecoveryPoint:
    path: Path
    document_id: str
    document_name: str
    saved_at: datetime
    size: int


class AutosaveManager:
    """Autosave explícito, validado e recuperável; não cria threads ocultas.

    Cada geração é um pacote `.srscene` completo. Gerações corrompidas nunca
    contam para a retenção das cópias válidas e um RecoveryPoint só pode
    restaurar o mesmo documento que declarou ao ser descoberto.
    """

    def __init__(self, root: str | Path, *, generations: int = 8) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.generations = max(2, int(generations))
        self._lock = RLock()

    def save(self, document: GraphicsDocument) -> Path:
        with self._lock:
            folder = self.root / _safe_id(document.id)
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            path = folder / f"{stamp}.srscene"
            save_package(document, path, embed_local_assets=False)
            # Reabra antes de promover a geração a `latest`. Assim uma falha de
            # armazenamento/zip jamais substitui o ponteiro para um recovery
            # point conhecido como íntegro.
            verified = load_package(path)
            if verified.id != document.id:
                path.unlink(missing_ok=True)
                raise ValueError("Autosave validado pertence a outro documento")
            _atomic_json(
                folder / "autosave.json",
                {
                    "document_id": document.id,
                    "document_name": document.name,
                    "latest": path.name,
                    "saved_at": stamp,
                },
            )
            self._prune(folder)
            return path

    def latest(self, document_id: str) -> RecoveryPoint | None:
        points = self._points(self.root / _safe_id(document_id))
        return points[0] if points else None

    def recover(self, point: RecoveryPoint, *, extract_assets_to: str | Path | None = None) -> GraphicsDocument:
        with self._lock:
            document = load_package(point.path, extract_assets_to=extract_assets_to)
            if document.id != point.document_id:
                raise ValueError("Recovery point não pertence ao documento informado")
            return document

    def list_recovery_points(self, document_id: str | None = None) -> list[RecoveryPoint]:
        if document_id:
            return self._points(self.root / _safe_id(document_id))
        out: list[RecoveryPoint] = []
        for folder in self.root.iterdir():
            if folder.is_dir():
                out.extend(self._points(folder))
        return sorted(out, key=lambda item: item.saved_at, reverse=True)

    def _points(self, folder: Path) -> list[RecoveryPoint]:
        if not folder.is_dir():
            return []
        points: list[RecoveryPoint] = []
        for path in folder.glob("*.srscene"):
            try:
                document = load_package(path)
                stat = path.stat()
                saved = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                points.append(RecoveryPoint(path, document.id, document.name, saved, stat.st_size))
            except (OSError, ValueError, KeyError):
                # Recovery incompleto/corrompido não entra na lista nem ocupa
                # uma geração válida. O arquivo é preservado para diagnóstico.
                continue
        return sorted(points, key=lambda item: item.saved_at, reverse=True)

    def _prune(self, folder: Path) -> None:
        # Retenha N recovery points *válidos*. Um arquivo corrompido recente não
        # pode fazer uma cópia boa mais antiga ser apagada.
        valid = self._points(folder)
        for old in valid[self.generations :]:
            old.path.unlink(missing_ok=True)


def _safe_id(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_")[:96] or "project"


def _atomic_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
