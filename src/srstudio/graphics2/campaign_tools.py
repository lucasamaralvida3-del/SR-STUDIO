"""Campaign artwork and color variants for existing editable Smart Slots.

No new slot family is introduced. Background and seal come from imported
local assets, embedded into the .srscene by the existing package saver.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlsplit
import mimetypes
import re
import unicodedata

from .model import AssetRef, GraphicsNode, NodeKind, Transform

BLUE = "#105594"
GREEN = "#075D08"
COFFEE = "#78441F"
MEAT = "#851B22"
BARBECUE = "#B32D18"
# Keep campaigns and color variants separate from Smart Slot families.
CAMPAIGNS = {
    "terca-verde": {"label": "Terça Verde", "theme": GREEN},
    "quarta-cafe": {"label": "Quarta Café com Pão", "theme": COFFEE},
    "quinta-file": {"label": "Quinta Filé", "theme": MEAT},
    "churrasco": {"label": "Churrasco e Açougue", "theme": BARBECUE},
}
THEMES = {"azul": BLUE, **{key: item["theme"] for key, item in CAMPAIGNS.items()}}


def _canonical_key(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).lower())
                   if not unicodedata.combining(c)).replace(" ", "_").replace("-", "_")


def parse_promo_date(value):
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, (int, float)) and 35000 <= value <= 70000:
        return (datetime(1899, 12, 30) + timedelta(days=int(value))).strftime("%d/%m/%Y")
    raw = str(value).strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw[:10], pattern).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return ""


def detect_sheet_date(document):
    """Only use a unique, explicitly named validity/promotion date."""
    keys = {"data_promocao", "data_da_promocao", "data_da_oferta",
            "data_oferta", "validade", "data_validade", "promo_date",
            "promotion_date", "valid_on", "data_inicio", "data_inicial"}
    values = []
    objects = [document.metadata]
    objects.extend(x for x in (document.metadata.get("products") or []) if isinstance(x, dict))
    for obj in objects:
        for key, value in obj.items():
            if _canonical_key(key) in keys:
                formatted = parse_promo_date(value)
                if formatted:
                    values.append(formatted)
    distinct = set(values)
    return next(iter(distinct)) if len(distinct) == 1 else ""


def _asset_for_file(document, path):
    raw = str(path)
    # Qt FileDialog emits file:///C:/... on Windows, not a native Path.
    if raw.startswith("file:"):
        url = urlsplit(raw)
        if url.scheme != "file" or url.netloc not in ("", "localhost"):
            raise ValueError("A imagem deve ser um arquivo local.")
        raw = unquote(url.path)
        if re.match(r"^/[A-Za-z]:/", raw):
            raw = raw[1:]
    source = Path(raw).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError("Selecione um arquivo JPG, PNG ou WebP existente.")
    digest = sha256(source.read_bytes()).hexdigest()
    for existing in document.assets.values():
        if existing.sha256 == digest and existing.kind == "image":
            return existing.id
    asset = AssetRef(kind="image", source=str(source),
                     mime=mimetypes.guess_type(str(source))[0] or "image/png",
                     sha256=digest)
    document.add_asset(asset)
    return asset.id


def apply_campaign_art(session, kind, path, *, campaign_id=None):
    if kind not in ("background", "seal"):
        raise ValueError("Elemento da campanha não reconhecido.")
    page = session.page
    campaign_id = str(campaign_id or page.metadata.get("campaign_id") or "terca-verde")
    if campaign_id not in CAMPAIGNS:
        raise ValueError("Campanha não reconhecida.")
    asset_id = _asset_for_file(session.document, path)
    key = "campaign_" + kind + "_node"
    with session.transaction("Aplicar arte promocional " + kind):
        node = page.node(str(page.metadata.get(key) or ""))
        if node is None:
            if kind == "background":
                rect = (0, 0, page.width, page.height)
                style, z = {"fit": "fill"}, -950
            else:
                # The supplied reference: top center/right, clear of SR logo.
                rect = (page.width * .355, page.height * .041,
                        page.width * .615, page.height * .345)
                style, z = {"fit": "contain"}, 95
            node = GraphicsNode(
                kind=NodeKind.IMAGE,
                name=CAMPAIGNS[campaign_id]["label"] + " · " + ("Fundo" if kind == "background" else "Selo"),
                transform=Transform(x=rect[0], y=rect[1], width=rect[2], height=rect[3]),
                z_index=z, style=style,
                metadata={"campaign_art": kind, "campaign_id": campaign_id},
            )
            page.add_node(node)
            page.metadata[key] = node.id
        node.asset_id = asset_id
        node.visible = True
        node.name = CAMPAIGNS[campaign_id]["label"] + " · " + ("Fundo" if kind == "background" else "Selo")
        node.metadata["campaign_id"] = campaign_id
        page.metadata["campaign_id"] = campaign_id
        if kind == "background":
            update_campaign_date(session.document, page)
    return node.id


def update_campaign_date(document, page, *, mode=None, manual_date=None):
    if mode not in (None, "manual", "auto"):
        raise ValueError("Modo de data deve ser manual ou automático.")
    if mode:
        page.metadata["campaign_date_mode"] = mode
    current_mode = page.metadata.get("campaign_date_mode") or "auto"
    if manual_date is not None:
        parsed = parse_promo_date(manual_date)
        if manual_date and not parsed:
            raise ValueError("Data inválida. Use DD/MM/AAAA.")
        page.metadata["campaign_manual_date"] = parsed
    displayed = (page.metadata.get("campaign_manual_date") or "") if current_mode == "manual" else detect_sheet_date(document)
    key = "campaign_date_node"
    node = page.node(str(page.metadata.get(key) or ""))
    if node is None:
        node = GraphicsNode(kind=NodeKind.TEXT, name="Data da promoção",
            text="", z_index=110,
            transform=Transform(x=page.width * .091, y=page.height * .265,
                                width=page.width * .176, height=page.height * .0178),
            style={"font_family": "Arial", "font_size": 15, "font_size_unit": "px",
                   "font_weight": 700, "color": "#FFFFFF", "align": "center",
                   "v_align": "center", "fit_inside_box": True,
                   "single_line": True, "nowrap": True, "min_font_size": 9},
            metadata={"campaign_id": str(page.metadata.get("campaign_id") or "terca-verde"), "campaign_date": True})
        page.add_node(node)
        page.metadata[key] = node.id
    node.text = displayed
    node.metadata["campaign_id"] = str(page.metadata.get("campaign_id") or "terca-verde")
    page.metadata["campaign_date_display"] = displayed
    return displayed


def set_campaign_date(session, *, mode="auto", value=None):
    with session.transaction("Atualizar validade da promoção"):
        return update_campaign_date(session.document, session.page,
                                    mode=mode, manual_date=value)


def apply_slot_theme(session, theme, slot_ids=None, *, entire_page=False):
    """Recolor existing art only; never replace slots or their products."""
    theme = str(theme).strip().lower()
    if theme in THEMES:
        target = THEMES[theme]
    elif re.fullmatch(r"#[0-9a-f]{6}", theme):
        target = theme.upper()
    else:
        raise ValueError("Escolha Azul, Terça Verde ou uma cor hexadecimal #RRGGBB.")
    page = session.page
    palette = {value.upper() for value in THEMES.values()}
    for existing in page.slots.values():
        previous = str(existing.metadata.get("color_hex") or "").upper()
        if re.fullmatch(r"#[0-9A-F]{6}", previous):
            palette.add(previous)
    slots = []
    for slot in page.slots.values():
        if not slot.metadata.get("manual_item_slot"):
            continue
        if entire_page or (slot_ids and slot.id in slot_ids):
            slots.append(slot)
    with session.transaction("Alterar cores dos Smart Slots"):
        if entire_page:
            page.metadata["slot_theme"] = theme
        recolored = set()
        for slot in slots:
            slot.metadata["color_theme"] = theme
            slot.metadata["color_hex"] = target
            root_id = str(slot.metadata.get("root_node_id") or "")
            for nid in page.descendants(root_id):
                node = page.node(nid)
                if node is None:
                    continue
                for key in ("fill", "stroke", "color"):
                    value = node.style.get(key)
                    if isinstance(value, str) and value.upper() in palette:
                        node.style[key] = target
                        recolored.add(nid)
        # Continuous Multi ribbon and separators live above their child cells.
        parent_ids = {str(s.metadata.get("multi_parent_id") or "") for s in slots}
        for parent_id in parent_ids:
            if not parent_id:
                continue
            parent = page.node(parent_id)
            if parent is None:
                continue
            for node_id in page.descendants(parent_id):
                node = page.node(node_id)
                if node is None or not node.metadata.get("multi_item_decoration"):
                    continue
                for key in ("fill", "stroke", "color"):
                    color = node.style.get(key)
                    if isinstance(color, str) and color.upper() in palette:
                        node.style[key] = target
                        recolored.add(node_id)
    return len(slots)


def apply_default_slot_theme(session, slot_ids):
    theme = str(session.page.metadata.get("slot_theme") or "azul")
    if theme != "azul":
        return apply_slot_theme(session, theme, list(slot_ids))
    return 0
