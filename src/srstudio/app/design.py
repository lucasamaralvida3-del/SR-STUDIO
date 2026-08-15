from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Colors:
    # Brand / application chrome
    sidebar: str = "#082D67"
    sidebar_dark: str = "#061F49"
    sidebar_hover: str = "#103C7F"
    sidebar_active: str = "#1657C7"
    sidebar_text: str = "#EAF2FF"
    sidebar_muted: str = "#AFC7EA"

    # Primary SR blue
    primary: str = "#1559D6"
    primary_hover: str = "#104AB7"
    primary_pressed: str = "#0C3C95"
    primary_soft: str = "#EAF1FF"
    primary_soft_hover: str = "#DCE8FF"

    # High-frequency production modes
    promotion: str = "#1767E8"
    promotion_hover: str = "#0F56C9"
    promotion_soft: str = "#EAF2FF"
    wholesale: str = "#123F78"
    wholesale_hover: str = "#0B3262"
    wholesale_soft: str = "#E9F0F8"

    # Semantic tones
    success: str = "#169B62"
    success_soft: str = "#E9F8F1"
    warning: str = "#C98505"
    warning_soft: str = "#FFF5DB"
    danger: str = "#D33B4D"
    danger_soft: str = "#FDECEF"
    info: str = "#3478D4"
    info_soft: str = "#EAF3FF"
    purple: str = "#7557C8"
    purple_soft: str = "#F0ECFF"

    # Neutral canvas
    bg: str = "#F3F6FA"
    surface: str = "#FFFFFF"
    surface_alt: str = "#F8FAFD"
    surface_hover: str = "#F3F7FC"
    surface_pressed: str = "#EAF0F8"
    border: str = "#DFE6EF"
    border_strong: str = "#C9D4E3"
    shadow: str = "#DCE4EF"

    # Typography
    text: str = "#152033"
    text_muted: str = "#657186"
    text_subtle: str = "#8C98AA"
    text_on_primary: str = "#FFFFFF"
    selection: str = "#DCE8FF"


COLORS = Colors()

SPACING = {
    "2xs": 2,
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "2xl": 32,
    "3xl": 40,
}

RADIUS = {
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
}

FONT = {
    "family": "Segoe UI",
    "display": 28,
    "page_title": 22,
    "title": 20,
    "section": 14,
    "body": 10,
    "small": 9,
    "micro": 8,
}

LAYOUT = {
    "sidebar_width": 244,
    "topbar_height": 72,
    "page_pad_x": 28,
    "page_pad_y": 24,
    "content_max": 1500,
}

NAVIGATION = (
    ("Início", "⌂"),
    ("Central 5.0", "◈"),
    ("Encartes Studio", "▣"),
    ("Banco de Produtos", "◇"),
    ("Planilhas", "▦"),
    ("Modelos", "▤"),
    ("Validação", "✓"),
    ("Exportação", "⇧"),
    ("SR IA", "✦"),
    ("Configurações", "⚙"),
    ("Promoções", "⚡"),
    ("Atacado", "▦"),
)

NAV_SECTIONS = (
    ("WORKSPACE", ("Início", "Encartes Studio", "Central 5.0")),
    ("CONTEÚDO", ("Banco de Produtos", "Planilhas", "Modelos")),
    ("FINALIZAÇÃO", ("Validação", "Exportação", "SR IA")),
    ("SISTEMA", ("Configurações",)),
)

NAV_ICONS = dict(NAVIGATION)

PAGE_META = {
    "Promoções": ("Cartazes de Promoção", "Geração rápida de ofertas e campanhas promocionais"),
    "Atacado": ("Cartazes de Atacado", "Geração de cartazes com varejo, atacado e quantidade"),
    "Início": ("Início", "Visão geral do projeto e atalhos rápidos"),
    "Central 5.0": ("Central 5.0", "Saúde, integridade e operação do projeto"),
    "Encartes Studio": ("Encartes Studio", "Editor visual da campanha"),
    "Banco de Produtos": ("Banco de Produtos", "Catálogo e memória local de produtos"),
    "Planilhas": ("Planilhas", "Importação e leitura de dados comerciais"),
    "Modelos": ("Modelos", "Templates SR e layouts aprendidos"),
    "Validação": ("Validação", "Qualidade e preflight da campanha"),
    "Exportação": ("Exportação", "Arquivos para impressão e canais digitais"),
    "SR IA": ("SR IA", "Assistente inteligente do Studio"),
    "Configurações": ("Configurações", "Preferências e infraestrutura local"),
}
