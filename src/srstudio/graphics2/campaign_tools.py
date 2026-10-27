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

# Placement is normalized to the page and calibrated to the supplied
# promotional poster examples. The SR logo is already on each background.
# Left ~0-.33 is kept clear for the printed SR mark.
SEAL_PLACEMENTS = {
    "terca-verde": (.35, .019, .64, .345),
    "quarta-cafe": (.33, .026, .66, .345),
    "quinta-file": (.38, .020, .60, .350),
    "churrasco": (.38, .024, .60, .350),
}

def _campaign_art_bounds(page, kind, campaign_id, path):
    if kind == "background":
        return (0.0, 0.0, page.width, page.height)
    x, y, w, h = SEAL_PLACEMENTS[campaign_id]
    if str(path).lower().endswith("acougue-premiado.webp"):
        x, y, w, h = (.49, .095, .47, .20)
    return (page.width * x, page.height * y, page.width * w, page.height * h)


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
            "data_oferta", "validade", "validity", "data_validade", "promo_date",
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


def local_campaign_path(path):
    """Normalize native paths and file:// URLs emitted by Qt FileDialog."""
    raw = str(path)
    if raw.startswith("file:"):
        url = urlsplit(raw)
        if url.scheme != "file" or url.netloc not in ("", "localhost"):
            raise ValueError("A imagem deve ser um arquivo local.")
        raw = unquote(url.path)
        if re.match(r"^/[A-Za-z]:/", raw):
            raw = raw[1:]
    return Path(raw).expanduser().resolve()


def _asset_for_file(document, path):
    source = local_campaign_path(path)
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
        rect = _campaign_art_bounds(page, kind, campaign_id, path)
        # Cover fills the entire page without stretching product imagery.
        # Seal uses contain for native aspect ratio and transparency.
        style, z = ({"fit": "cover"}, -950) if kind == "background" else ({"fit": "contain"}, 95)
        if node is None:
            node = GraphicsNode(
                kind=NodeKind.IMAGE,
                name=CAMPAIGNS[campaign_id]["label"] + " · " + ("Fundo" if kind == "background" else "Selo"),
                transform=Transform(x=rect[0], y=rect[1], width=rect[2], height=rect[3]),
                z_index=z, style=style,
                metadata={"campaign_art": kind, "campaign_id": campaign_id},
            )
            page.add_node(node)
            page.metadata[key] = node.id
        # Re-selecting a new campaign resets dimensions/position to its own
        # reference, preventing old placements from leaking into new campaigns.
        node.transform.x, node.transform.y = rect[0], rect[1]
        node.transform.width, node.transform.height = rect[2], rect[3]
        node.style.update(style)
        node.z_index = z
        node.asset_id = asset_id
        node.visible = True
        node.name = CAMPAIGNS[campaign_id]["label"] + " · " + ("Fundo" if kind == "background" else "Selo")
        node.metadata["campaign_id"] = campaign_id
        page.metadata["campaign_id"] = campaign_id
        if kind == "background":
            update_campaign_date(session.document, page)
    return node.id


def apply_campaign_preset(session, background_id: str) -> dict:
    """One-click composition: full background + matching default seal + palette.

    The operation is undoable as ONE transaction; existing product slots stay
    bound and are recolored in place, never replaced.
    """
    from .builtin_campaign_catalog import (
        find_builtin_campaign_asset, default_seal_for_campaign,
    )
    background = find_builtin_campaign_asset(background_id, expected_kind="background")
    campaign = background["campaign_id"]
    if campaign not in CAMPAIGNS:
        raise ValueError("Campanha desconhecida.")
    seal = default_seal_for_campaign(campaign)
    # Resolve both paths before touching the scene, then use one atomic Undo.
    with session.transaction("Aplicar campanha completa"):
        background_node_id = apply_campaign_art(
            session, "background", background["path"], campaign_id=campaign)
        seal_node_id = apply_campaign_art(
            session, "seal", seal["path"], campaign_id=campaign)
        apply_slot_theme(session, campaign, entire_page=True)
        session.page.metadata["campaign_background_asset"] = background["id"]
        session.page.metadata["campaign_seal_asset"] = seal["id"]
    return {"campaign_id": campaign, "background_node_id": background_node_id,
            "seal_node_id": seal_node_id, "background_id": background["id"],
            "seal_id": seal["id"]}


def apply_campaign_seal(session, seal_id: str) -> dict:
    """Switch logo variant without changing the background or product slots."""
    from .builtin_campaign_catalog import find_builtin_campaign_asset
    seal = find_builtin_campaign_asset(seal_id, expected_kind="seal")
    # The current background determines campaign; mixing unrelated artwork
    # is prevented because it produces visually broken posters.
    current = str(session.page.metadata.get("campaign_id") or "")
    if current and current != seal["campaign_id"]:
        raise ValueError("Selo de outra campanha: selecione o fundo correspondente.")
    with session.transaction("Trocar selo da promoção"):
        node_id = apply_campaign_art(
            session, "seal", seal["path"], campaign_id=seal["campaign_id"])
        session.page.metadata["campaign_seal_asset"] = seal["id"]
    return {"seal_id": seal["id"], "seal_node_id": node_id}


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
