from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

DEFAULT_FALLBACKS: dict[str, tuple[str, ...]] = {
    "anton": ("Impact", "Arial Narrow", "Arial"),
    "bebas neue": ("Arial Narrow", "Impact", "Arial"),
    "montserrat": ("Arial", "Segoe UI"),
    "poppins": ("Arial", "Segoe UI"),
    "league spartan": ("Arial Black", "Arial"),
    "oswald": ("Arial Narrow", "Impact", "Arial"),
}


@dataclass(slots=True, frozen=True)
class FontResolution:
    requested: str
    resolved: str
    exact: bool
    warning: str = ""


@dataclass(slots=True)
class FontCatalog:
    installed: set[str] = field(default_factory=set)
    fallbacks: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_FALLBACKS))

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "FontCatalog":
        return cls(installed={str(name).strip() for name in names if str(name).strip()})

    def resolve(self, requested: str, *, allow_fallback: bool = True) -> FontResolution:
        requested = str(requested or "").strip()
        if not requested: return FontResolution("", "", False, "Fonte não informada.")
        canonical = {name.casefold(): name for name in self.installed}; exact = canonical.get(requested.casefold())
        if exact: return FontResolution(requested, exact, True)
        if not allow_fallback: return FontResolution(requested, "", False, f"Fonte original não encontrada: {requested}")
        for candidate in self.fallbacks.get(requested.casefold(), ()):
            found = canonical.get(candidate.casefold())
            if found: return FontResolution(requested, found, False, f"Fonte original ausente: {requested}. Visualização usando {found}; a geometria original foi preservada.")
        return FontResolution(requested, "", False, f"Fonte original não encontrada e sem fallback aprovado: {requested}")

    def missing(self, requested_fonts: Iterable[str]) -> list[str]:
        canonical = {name.casefold() for name in self.installed}
        return sorted({name for name in requested_fonts if name and name.casefold() not in canonical})
