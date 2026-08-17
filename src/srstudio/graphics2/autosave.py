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
    """Autosave explícito e recuperável; não cria threads ocultas."""

    def __init__(
        self,
        root: str | Path,
        *,
        generations: int = 8,
        embed_local_assets: bool = False,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.generations = max(2, int(generations))
        self.embed_local_assets = bool(embed_local_assets)
        self._lock = RLock()

    def save(self, document: GraphicsDocument) -> Path:
        with self._lock:
            folder = self.root / _safe_id(document.id)
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            path = folder / f"{stamp}.srscene"
            save_package(document, path, embed_local_assets=self.embed_local_assets)
            _atomic_json(
                folder / "autosave.json",
                {
                    "document_id": document.id,
                    "document_name": document.name,
                    "latest": path.name,
                    "saved_at": stamp,
                    "embed_local_assets": self.embed_local_assets,
                },
            )
            self._prune(folder)
            return path

    def latest(self, document_id: str) -> RecoveryPoint | None:
        points = self._points(self.root / _safe_id(document_id))
        return points[0] if points else None

    def latest_any(self) -> RecoveryPoint | None:
        points = self.list_recovery_points()
        return points[0] if points else None

    def recover(self, point: RecoveryPoint, *, extract_assets_to: str | Path | None = None) -> GraphicsDocument:
        return load_package(point.path, extract_assets_to=extract_assets_to)

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
                saved = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                points.append(RecoveryPoint(path, document.id, document.name, saved, path.stat().st_size))
            except (OSError, ValueError, KeyError):
                pass
        return sorted(points, key=lambda item: item.saved_at, reverse=True)

    def _prune(self, folder: Path) -> None:
        paths = sorted(folder.glob("*.srscene"), key=lambda path: path.stat().st_mtime, reverse=True)
        for old in paths[self.generations:]:
            old.unlink(missing_ok=True)


def _safe_id(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_")[:96] or "project"


def _atomic_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
