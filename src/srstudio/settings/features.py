from __future__ import annotations

import json
import os
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
        if self.path.exists():
            try: raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError, json.JSONDecodeError): raw = None
            if isinstance(raw, dict): flags.merge(raw)

        # A Beta 7.31 pode ativar o Graphics2 sem reescrever preferências locais.
        # O launcher Beta injeta estas variáveis somente no processo Beta; Stable
        # e execuções normais continuam obedecendo as flags persistidas.
        if str(os.environ.get("SR_GRAPHICS_ENGINE_2_BETA") or "").strip() == "1":
            flags.set("graphics_engine_2", True)
            gpu = str(os.environ.get("SR_GRAPHICS_ENGINE_2_GPU") or "1").strip().lower()
            flags.set("graphics_engine_2_gpu", gpu not in {"0", "false", "no", "off"})
        return flags
    def save(self, flags: FeatureFlags) -> None:
        self.path.write_text(json.dumps(flags.values, ensure_ascii=False, indent=2), encoding="utf-8")
