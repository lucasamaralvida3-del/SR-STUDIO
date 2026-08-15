from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from srstudio.core.models import StudioProject
from srstudio.projects.store import ProjectStore


@dataclass(slots=True)
class SessionState:
    dirty: bool = False
    last_saved_at: float = 0.0
    last_autosaved_at: float = 0.0
    project_path: str = ""


class ProjectSession:
    """Coordena dirty state, save, autosave e snapshots com detecção por conteúdo."""

    def __init__(
        self,
        project: StudioProject,
        store: ProjectStore,
        autosave_dir: str | Path,
        autosave_interval: float = 60.0,
    ) -> None:
        self.project = project
        self.store = store
        self.autosave_dir = Path(autosave_dir)
        self.autosave_dir.mkdir(parents=True, exist_ok=True)
        self.interval = max(10.0, float(autosave_interval))
        self.state = SessionState()
        self._saved_signature = self._signature()
        self._autosave_signature = self._saved_signature

    def mark_dirty(self) -> None:
        self.state.dirty = True

    def refresh_dirty(self) -> bool:
        self.state.dirty = self._signature() != self._saved_signature
        return self.state.dirty

    def save(self, path: str | Path | None = None) -> Path:
        raw_target = path or self.state.project_path
        if not raw_target:
            raise ValueError("Caminho do projeto não definido")
        target = Path(raw_target)
        self.store.save(self.project, target)
        now = time.time()
        self.state.project_path = str(target)
        self.state.last_saved_at = now
        self._saved_signature = self._signature()
        self._autosave_signature = self._saved_signature
        self.state.dirty = False
        return target

    def autosave(self, force: bool = False) -> Path | None:
        current_signature = self._signature()
        self.state.dirty = current_signature != self._saved_signature
        changed_since_autosave = current_signature != self._autosave_signature
        if not force and not changed_since_autosave:
            return None
        now = time.time()
        if not force and now - self.state.last_autosaved_at < self.interval:
            return None
        target = self.autosave_dir / f"{self.project.id}.autosave.srproject"
        self.store.save(self.project, target)
        self.state.last_autosaved_at = now
        self._autosave_signature = current_signature
        return target

    def snapshot(self, label: str = "manual") -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label) or "snapshot"
        target = self.autosave_dir / "snapshots" / self.project.id / f"{stamp}-{safe}.srproject"
        target.parent.mkdir(parents=True, exist_ok=True)
        self.store.save(self.project, target)
        return target

    def recovery_candidates(self) -> tuple[Path, ...]:
        candidates = list(self.autosave_dir.glob("*.autosave.srproject"))
        candidates.extend(self.autosave_dir.glob("snapshots/*/*.srproject"))
        return tuple(sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True))

    def _signature(self) -> str:
        payload = json.dumps(self.project.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
