from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class StudioSettings:
    theme: str = "light"
    autosave_seconds: int = 45
    history_limit: int = 300
    default_export_profile: str = "print-high"
    beta_features: bool = True
    show_safe_area: bool = True
    snap_to_guides: bool = True
    snap_distance: int = 8
    image_cache_mb: int = 512
    diagnostics_level: str = "normal"


class SettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SR Studio 5"
        self.path = Path(path) if path else root / "settings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> StudioSettings:
        if not self.path.exists():
            return StudioSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = StudioSettings.__dataclass_fields__.keys()
            return StudioSettings(**{k: v for k, v in raw.items() if k in allowed})
        except Exception:
            return StudioSettings()

    def save(self, settings: StudioSettings) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
