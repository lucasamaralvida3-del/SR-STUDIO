from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FLAGS = {
    "sr_ai": True,
    "pptx_semantic_import": True,
    "advanced_layers": True,
    "smart_guides": True,
    "graphics_engine_2": False,
    "graphics_engine_2_gpu": False,
    "experimental_template_learning": False,
    "developer_mode": False,
}


@dataclass(slots=True)
class FeatureFlags:
    values: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_FLAGS))
    def enabled(self, name: str) -> bool: return bool(self.values.get(name, False))
    def set(self, name: str, enabled: bool) -> None: self.values[name] = bool(enabled)
    def merge(self, values: dict[str, bool]) -> None:
        for key, value in values.items(): self.values[str(key)] = bool(value)


class FeatureFlagStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
    def load(self) -> FeatureFlags:
        flags = FeatureFlags()
        if not self.path.exists(): return flags
        try: raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError): return flags
        if isinstance(raw, dict): flags.merge(raw)
        return flags
    def save(self, flags: FeatureFlags) -> None:
        self.path.write_text(json.dumps(flags.values, ensure_ascii=False, indent=2), encoding="utf-8")
