from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import os
import sys
import threading

DEFAULT_FALLBACKS: dict[str, tuple[str, ...]] = {
    "anton": ("Impact", "Arial Narrow", "Arial"),
    "bebas neue": ("Arial Narrow", "Impact", "Arial"),
    "montserrat": ("Arial", "Segoe UI"),
    "poppins": ("Arial", "Segoe UI"),
    "league spartan": ("Arial Black", "Arial"),
    "oswald": ("Arial Narrow", "Impact", "Arial"),
}

_QT_FONT_CACHE: dict[str, tuple[str, ...]] = {}
_GUI_APPLICATION = None


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
        if not requested:
            return FontResolution("", "", False, "Fonte não informada.")
        canonical = {name.casefold(): name for name in self.installed}
        exact = canonical.get(requested.casefold())
        if exact:
            return FontResolution(requested, exact, True)
        if not allow_fallback:
            return FontResolution(requested, "", False, f"Fonte original não encontrada: {requested}")
        for candidate in self.fallbacks.get(requested.casefold(), ()):
            found = canonical.get(candidate.casefold())
            if found:
                return FontResolution(
                    requested,
                    found,
                    False,
                    f"Fonte original ausente: {requested}. Visualização usando {found}; a geometria original foi preservada.",
                )
        return FontResolution(requested, "", False, f"Fonte original não encontrada e sem fallback aprovado: {requested}")

    def missing(self, requested_fonts: Iterable[str]) -> list[str]:
        canonical = {name.casefold() for name in self.installed}
        return sorted({name for name in requested_fonts if name and name.casefold() not in canonical})


@dataclass(slots=True)
class QtFontRegistrationReport:
    loaded_paths: list[str] = field(default_factory=list)
    families: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.warnings


def embedded_font_entries(document: Any) -> list[dict[str, Any]]:
    metadata = dict(getattr(document, "metadata", {}) or {})
    direct = metadata.get("embedded_fonts")
    if isinstance(direct, list):
        return [dict(item) for item in direct if isinstance(item, dict)]
    legacy = metadata.get("legacy_settings")
    if isinstance(legacy, dict) and isinstance(legacy.get("canva_embedded_fonts"), list):
        return [dict(item) for item in legacy["canva_embedded_fonts"] if isinstance(item, dict)]
    return []


def ensure_qgui_application():
    """Garante um QGuiApplication antes de usar fontes/rasterização Qt.

    O host Qt já possui a aplicação. O CLI/harness pode chamar o renderer sem
    criá-la; nesse caso ela é criada somente na thread principal. Em worker do
    host, uma instância já existente precisa ser reutilizada — nunca construímos
    um QGuiApplication secundário em background.
    """

    global _GUI_APPLICATION
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication

    existing = QCoreApplication.instance()
    if existing is not None:
        if not isinstance(existing, QGuiApplication):
            raise RuntimeError(
                "SR Graphics Engine 2 requer QGuiApplication; o processo possui apenas QCoreApplication."
            )
        _GUI_APPLICATION = existing
        return existing

    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError(
            "SR Graphics Engine 2 não pode criar QGuiApplication em thread de worker; "
            "inicialize o host Qt na thread principal antes de renderizar."
        )

    if sys.platform.startswith("linux"):
        if not os.environ.get("QT_QPA_PLATFORM") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

    _GUI_APPLICATION = QGuiApplication(["sr-graphics-engine-2-render"])
    _GUI_APPLICATION.setApplicationName("SR Graphics Engine 2 Renderer")
    return _GUI_APPLICATION


def register_qt_document_fonts(document: Any) -> QtFontRegistrationReport:
    """Registra fontes PPTX e, antes disso, garante o runtime gráfico do Qt."""

    report = QtFontRegistrationReport()
    entries = embedded_font_entries(document)
    try:
        ensure_qgui_application()
    except ModuleNotFoundError as exc:
        if entries:
            report.warnings.append(f"Qt indisponível para registrar fontes embutidas: {exc}")
        return report

    if not entries:
        return report
    try:
        from PySide6.QtGui import QFontDatabase
    except Exception as exc:
        report.warnings.append(f"Qt indisponível para registrar fontes embutidas: {exc}")
        return report

    known_families: set[str] = set()
    for entry in entries:
        if not bool(entry.get("runtime_allowed", True)):
            family = str(entry.get("family") or "fonte")
            report.warnings.append(f"Fonte embutida '{family}' não permite registro automático.")
            continue
        raw_path = str(entry.get("extracted_path") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_file():
            report.warnings.append(f"Fonte embutida não encontrada no cache: {path}")
            continue
        cache_key = str(path.resolve())
        cached = _QT_FONT_CACHE.get(cache_key)
        if cached is None:
            font_id = QFontDatabase.addApplicationFont(cache_key)
            if font_id < 0:
                report.warnings.append(f"Qt não conseguiu carregar a fonte embutida: {path.name}")
                continue
            cached = tuple(str(name) for name in QFontDatabase.applicationFontFamilies(font_id))
            _QT_FONT_CACHE[cache_key] = cached
        report.loaded_paths.append(cache_key)
        known_families.update(cached)
    report.families = sorted(known_families)
    return report
