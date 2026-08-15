from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {".ttf", ".otf", ".ttc"}


@dataclass(frozen=True, slots=True)
class FontAsset:
    family: str
    path: str
    source: str = "user"


class FontCatalog:
    def __init__(self) -> None:
        self._fonts: dict[str, FontAsset] = {}
        self._substitutions: dict[str, str] = {}

    @staticmethod
    def _key(name: str) -> str:
        return " ".join(str(name or "").strip().lower().split())

    def register(self, family: str, path: str | Path, source: str = "user") -> FontAsset:
        asset = FontAsset(family=str(family).strip(), path=str(Path(path)), source=source)
        self._fonts[self._key(asset.family)] = asset
        return asset

    def scan(self, directories: Iterable[str | Path], source: str = "user") -> list[FontAsset]:
        found: list[FontAsset] = []
        for directory in directories:
            root = Path(directory)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    family = path.stem.replace("_", " ").replace("-", " ").strip()
                    found.append(self.register(family, path, source=source))
        return found

    def set_substitution(self, missing_family: str, replacement_family: str) -> None:
        self._substitutions[self._key(missing_family)] = replacement_family

    def resolve(self, family: str) -> FontAsset | None:
        key = self._key(family)
        exact = self._fonts.get(key)
        if exact:
            return exact
        replacement = self._substitutions.get(key)
        if replacement:
            return self._fonts.get(self._key(replacement))
        return None

    def missing(self, families: Iterable[str]) -> list[str]:
        return sorted({family for family in families if family and self.resolve(family) is None})

    def all(self) -> list[FontAsset]:
        return sorted(self._fonts.values(), key=lambda item: item.family.lower())
