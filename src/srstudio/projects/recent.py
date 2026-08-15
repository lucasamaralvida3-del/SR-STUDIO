from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class RecentProject:
    path: str
    name: str
    last_opened: str
    favorite: bool = False
    thumbnail: str = ""


class RecentProjectsStore:
    def __init__(self, path: str | Path, limit: int = 30) -> None:
        self.path = Path(path)
        self.limit = max(5, limit)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[RecentProject]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        items: list[RecentProject] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                items.append(RecentProject(**item))
            except TypeError:
                continue
        return self._sort(items)

    def touch(self, project_path: str | Path, name: str | None = None, thumbnail: str = "") -> list[RecentProject]:
        normalized = str(Path(project_path).resolve())
        items = self.load()
        existing = next((item for item in items if item.path == normalized), None)
        now = datetime.now(timezone.utc).isoformat()
        if existing is None:
            existing = RecentProject(normalized, name or Path(normalized).stem, now, thumbnail=thumbnail)
            items.append(existing)
        else:
            existing.last_opened = now
            existing.name = name or existing.name
            existing.thumbnail = thumbnail or existing.thumbnail
        items = self._trim(self._sort(items))
        self._save(items)
        return items

    def set_favorite(self, project_path: str | Path, favorite: bool) -> None:
        normalized = str(Path(project_path).resolve())
        items = self.load()
        for item in items:
            if item.path == normalized:
                item.favorite = bool(favorite)
                break
        self._save(self._sort(items))

    def remove_missing(self) -> list[RecentProject]:
        items = [item for item in self.load() if Path(item.path).exists()]
        self._save(items)
        return items

    def _save(self, items: list[RecentProject]) -> None:
        self.path.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")

    def _trim(self, items: list[RecentProject]) -> list[RecentProject]:
        favorites = [item for item in items if item.favorite]
        normal = [item for item in items if not item.favorite][: max(0, self.limit - len(favorites))]
        return favorites + normal

    @staticmethod
    def _sort(items: list[RecentProject]) -> list[RecentProject]:
        return sorted(items, key=lambda item: (not item.favorite, item.last_opened), reverse=False)
