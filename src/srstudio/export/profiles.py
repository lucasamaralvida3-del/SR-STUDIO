from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExportProfile:
    key: str
    label: str
    format: str
    width: int | None = None
    height: int | None = None
    dpi: int = 300
    quality: int = 95
    bleed_mm: float = 0.0
    safe_margin_mm: float = 5.0
    flatten_transparency: bool = False


PROFILES = {
    "print-high": ExportProfile("print-high", "PDF Alta Qualidade", "pdf", dpi=300, bleed_mm=3.0, safe_margin_mm=5.0),
    "print-office": ExportProfile("print-office", "PDF Impressora", "pdf", dpi=200, safe_margin_mm=5.0),
    "pdf-light": ExportProfile("pdf-light", "PDF Leve", "pdf", dpi=144, quality=82, safe_margin_mm=4.0),
    "instagram-portrait": ExportProfile("instagram-portrait", "Instagram 1080 × 1350", "png", 1080, 1350, dpi=144, safe_margin_mm=0.0),
    "instagram-square": ExportProfile("instagram-square", "Instagram 1080 × 1080", "png", 1080, 1080, dpi=144, safe_margin_mm=0.0),
    "whatsapp": ExportProfile("whatsapp", "WhatsApp", "jpg", 1080, 1350, dpi=120, quality=90, safe_margin_mm=0.0),
}


def get_profile(key: str) -> ExportProfile:
    try:
        return PROFILES[key]
    except KeyError as exc:
        raise ValueError(f"Perfil de exportação desconhecido: {key}") from exc


def output_path(base: str | Path, profile: ExportProfile, page: int | None = None) -> Path:
    base = Path(base)
    suffix = ".jpg" if profile.format == "jpg" else f".{profile.format}"
    page_suffix = f"_p{page:02d}" if page is not None else ""
    return base.with_name(f"{base.stem}_{profile.key}{page_suffix}").with_suffix(suffix)
