from __future__ import annotations

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
    """Coordena dirty state, save, autosave e snapshots de recuperação."""

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

    def mark_dirty(self) -> None:
        self.state.dirty = True

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path or self.state.project_path)
        if not str(target):
            raise ValueError("Caminho do projeto não definido")
        self.store.save(self.project, target)
        now = time.time()
        self.state.project_path = str(target)
        self.state.last_saved_at = now
        self.state.dirty = False
        return target

    def autosave(self, force: bool = False) -> Path | None:
        if not self.state.dirty and not force:
            return None
        now = time.time()
        if not force and now - self.state.last_autosaved_at < self.interval:
            return None
        target = self.autosave_dir / f"{self.project.id}.autosave.srproject"
        self.store.save(self.project, target)
        self.state.last_autosaved_at = now
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
