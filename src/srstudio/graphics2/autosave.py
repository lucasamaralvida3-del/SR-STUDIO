from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Callable
import json
import os
import time
import zipfile

from .model import GraphicsDocument
from .package import load_package, save_package


@dataclass(slots=True, frozen=True)
class RecoveryPoint:
    path: Path
    document_id: str
    document_name: str
    saved_at: datetime
    size: int


def document_fingerprint(document: GraphicsDocument) -> str:
    """Deterministic scene fingerprint used only for dirty/autosave decisions."""
    payload = json.dumps(
        document.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


class AutosaveManager:
    """Autosave explícito, versionado e recuperável; não cria threads ocultas.

    ``save`` preserves the historical API and always creates a recovery point.
    ``save_if_changed`` is intended for a UI timer: it skips identical states and
    optionally enforces a minimum cadence. Autosaves always live under ``root``
    and therefore never overwrite the user's explicit ``.srscene`` project.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        generations: int = 8,
        interval_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.generations = max(2, int(generations))
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._clock = clock
        self._lock = RLock()
        self._last_fingerprint: dict[str, str] = {}
        self._last_attempt: dict[str, float] = {}

    def save(self, document: GraphicsDocument) -> Path:
        """Create a recovery generation immediately."""
        with self._lock:
            path = self._save_locked(document)
            self._last_fingerprint[document.id] = document_fingerprint(document)
            self._last_attempt[document.id] = self._clock()
            return path

    def save_if_changed(
        self,
        document: GraphicsDocument,
        *,
        min_interval_seconds: float | None = None,
    ) -> Path | None:
        """Create a recovery point only when content changed and cadence is due."""
        with self._lock:
            now = self._clock()
            interval = self.interval_seconds if min_interval_seconds is None else max(0.0, float(min_interval_seconds))
            last_attempt = self._last_attempt.get(document.id, float("-inf"))
            if now - last_attempt < interval:
                return None

            self._last_attempt[document.id] = now
            fingerprint = document_fingerprint(document)
            baseline = self._last_fingerprint.get(document.id)
            if baseline is None:
                latest = self.latest(document.id)
                if latest is not None:
                    try:
                        baseline = document_fingerprint(self.recover(latest))
                    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                        baseline = None
            if baseline == fingerprint:
                self._last_fingerprint[document.id] = fingerprint
                return None

            path = self._save_locked(document)
            self._last_fingerprint[document.id] = fingerprint
            return path

    def mark_current_state(self, document: GraphicsDocument) -> None:
        """Mark a manual-save/current state so an unchanged timer tick is skipped."""
        with self._lock:
            self._last_fingerprint[document.id] = document_fingerprint(document)
            self._last_attempt[document.id] = self._clock()

    def latest(self, document_id: str) -> RecoveryPoint | None:
        points = self._points(self.root / _safe_id(document_id))
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

    def has_newer_recovery(self, document_id: str, manual_project: str | Path | None) -> bool:
        """Return True only when a valid autosave is newer than the manual project."""
        latest = self.latest(document_id)
        if latest is None:
            return False
        if manual_project is None:
            return True
        manual = Path(manual_project)
        if not manual.exists():
            return True
        return latest.path.stat().st_mtime_ns > manual.stat().st_mtime_ns

    def clear(self, document_id: str) -> int:
        """Delete only autosave generations for one document, never manual files."""
        with self._lock:
            folder = self.root / _safe_id(document_id)
            removed = 0
            if folder.is_dir():
                for path in folder.glob("*.srscene"):
                    path.unlink(missing_ok=True)
                    removed += 1
                (folder / "autosave.json").unlink(missing_ok=True)
                try:
                    folder.rmdir()
                except OSError:
                    pass
            self._last_fingerprint.pop(document_id, None)
            self._last_attempt.pop(document_id, None)
            return removed

    def _save_locked(self, document: GraphicsDocument) -> Path:
        folder = self.root / _safe_id(document.id)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        path = folder / f"{stamp}.srscene"
        save_package(document, path, embed_local_assets=False)
        _atomic_json(
            folder / "autosave.json",
            {
                "document_id": document.id,
                "document_name": document.name,
                "latest": path.name,
                "saved_at": stamp,
                "fingerprint": document_fingerprint(document),
            },
        )
        self._prune(folder)
        return path

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
            except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile):
                # A damaged generation must not hide older valid recovery points.
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
