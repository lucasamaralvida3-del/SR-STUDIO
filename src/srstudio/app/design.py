from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Colors:
    sidebar: str = "#0B47B7"
    sidebar_dark: str = "#073A9B"
    sidebar_active: str = "#275FC6"
    primary: str = "#1459E7"
    primary_hover: str = "#0F4CCA"
    success: str = "#18B979"
    warning: str = "#F6A800"
    danger: str = "#E5484D"
    bg: str = "#F6F8FC"
    surface: str = "#FFFFFF"
    surface_alt: str = "#F8FAFD"
    border: str = "#E3E8F2"
    text: str = "#101828"
    text_muted: str = "#667085"
    text_on_primary: str = "#FFFFFF"
    selection: str = "#DDE8FF"


COLORS = Colors()

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "2xl": 32,
}

RADIUS = {
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
}

FONT = {
    "family": "Segoe UI",
    "title": 24,
    "section": 16,
    "body": 11,
    "small": 9,
}

NAVIGATION = (
    ("Início", "⌂"),
    ("Central 5.0", "⚡"),
    ("Encartes Studio", "▣"),
    ("Banco de Produtos", "◇"),
    ("Planilhas", "▦"),
    ("Modelos", "▤"),
    ("Validação", "✓"),
    ("Exportação", "⇧"),
    ("SR IA", "✦"),
    ("Configurações", "⚙"),
)
