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
# Exact median swatches sampled from the COLORED validity-city footer of
# each original 1080x1350 SR artwork. Ignore the yellow/white city text.
GREEN = "#0A6005"
COFFEE = "#704A33"
MEAT = "#460000"
BARBECUE = "#460000"
LEGACY_THEME_COLORS = frozenset({
    "#075D08", "#78441F", "#851B22", "#B32D18",
    "#105594", "#24518E", "#265398",
})
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

# Date boxes in the supplied original campaign artwork are NOT all in
# the same place. Keep one explicit, normalized contract per campaign.
# These rectangles may be calibrated from the actual reference images
# without changing any product or Smart Slot source templates.
DATE_PLACEMENTS = {
    # Fit INSIDE the printed date pill, below "VÁLIDAS SOMENTE DIA",
    # not over that fixed artwork label. Reference page is 1080x1350.
    "terca-verde": (.111, .282, .148, .016),
    "quarta-cafe": (.110, .282, .151, .016),
    "quinta-file": (.125, .282, .146, .016),
    "churrasco": (.130, .269, .146, .016),
}


def logo_safe_reserve(page, requested: float, *, gap: float = .028, document=None) -> float:
    """Return a campaign-aware reserved region ABOVE all layout Smart Slots.

    Derive the live seal's bottom edge from its real edited geometry; respect
    manual logo scaling/dragging. If the seal isn't in the scene yet but a
    campaign background is active, reserve the catalogue's seal placement.
    This helper never moves/resizes any logo, image, product or date.
    """
    required = float(requested)
    seal_id = str(page.metadata.get("campaign_seal_node") or "")
    seal = page.node(seal_id) if seal_id else None
    if seal is not None and seal.visible and seal.metadata.get("campaign_art") == "seal":
        bounds = seal.rect.normalized()
        visible_bottom = bounds.bottom
        if document is not None:
            # Campaign seals often contain large transparent margins. Reserve
            # only the real visible artwork (including anti-aliased edges),
            # not the entire PNG canvas. This never moves or clips the logo.
            from .image_autofit import fitted_product_source, visible_product_crop
            crop = visible_product_crop(fitted_product_source(document, seal))
            if crop:
                visible_bottom -= bounds.height * float(crop.get("b", 0.0))
        required = max(required, visible_bottom / page.height + gap)
    elif page.metadata.get("campaign_background_node"):
        campaign = str(page.metadata.get("campaign_id") or "")
        if campaign in SEAL_PLACEMENTS:
            _, y, _, h = SEAL_PLACEMENTS[campaign]
            required = max(required, y + h + gap)
    if required > .50:
        raise ValueError(
            "A logo ocupa mais da metade do encarte. Reduza ou reposicione "
            "a logo antes de aplicar o layout; nenhum elemento foi movido."
        )
    return required


def _footer_color_from_image(path) -> str | None:
    """Sample the actual footer BAR, away from the city/promotion lettering.

    The original template has a flat colored footer at 97.9–98.9% of page
    height. Two side patches exclude the typically centered city label.
    """
    try:
        from PIL import Image, ImageStat
        with Image.open(local_campaign_path(path)) as image:
            img = image.convert("RGB")
            width, height = img.size
            if min(width, height) < 40:
                return None
            y0, y1 = int(.979 * height), max(int(.989 * height), int(.979 * height) + 1)
            patches = (
                img.crop((int(.06 * width), y0, int(.22 * width), y1)),
                img.crop((int(.78 * width), y0, int(.94 * width), y1)),
            )
            sample = Image.new("RGB", (patches[0].width + patches[1].width, patches[0].height))
            sample.paste(patches[0], (0, 0))
            sample.paste(patches[1], (patches[0].width, 0))
            rgb = ImageStat.Stat(sample).median
            # Don't infer theme from posters with no solid footer (photos,
            # gradients, or out-of-template crops); use certified fallback.
            spread = ImageStat.Stat(sample).stddev
            if max(spread) > 17:
                return None
            return "#" + "".join(f"{round(v):02X}" for v in rgb)
    except (OSError, ValueError, TypeError):
        return None


def campaign_footer_theme(document, page, campaign_id: str) -> str:
    """Swatch the active background for its city footer, not the text."""
    fallback = THEMES[campaign_id]
    image_id = str(page.metadata.get("campaign_background_node") or "")
    background = page.node(image_id)
    if background is None or background.metadata.get("campaign_id") != campaign_id:
        return fallback
    asset = document.assets.get(str(background.asset_id or ""))
    if asset is None:
        return fallback
    measured = _footer_color_from_image(asset.source)
    if not measured:
        return fallback
    # JPEG→WebP poster packing may change RGB by 1–3 levels. Retain the
    # certified original swatch if measured and source differ only by codec.
    distance = max(abs(int(measured[i:i + 2], 16) - int(fallback[i:i + 2], 16))
                   for i in (1, 3, 5))
    return fallback if distance <= 3 else measured


def _date_geometry(page, campaign_id):
    x, y, width, height = DATE_PLACEMENTS.get(campaign_id, DATE_PLACEMENTS["terca-verde"])
    return page.width * x, page.height * y, page.width * width, page.height * height


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
        keep_manual_seal_geometry = (
            kind == "seal" and node.metadata.get("campaign_id") == campaign_id
            and node.asset_id == asset_id and node.visible
        )
        if not keep_manual_seal_geometry:
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
            transform=Transform(*_date_geometry(page, str(page.metadata.get("campaign_id") or "terca-verde"))),
            style={"font_family": "Impact", "font_size": 13, "font_size_unit": "pt",
                   "font_weight": 700, "color": "#FFFFFF", "align": "center",
                   "v_align": "center", "fit_inside_box": True,
                   "single_line": True, "nowrap": True, "min_font_size": 8},
            metadata={"campaign_id": str(page.metadata.get("campaign_id") or "terca-verde"), "campaign_date": True})
        page.add_node(node)
        page.metadata[key] = node.id
    campaign = str(page.metadata.get("campaign_id") or "terca-verde")
    # A new spreadsheet date must never drift into the campaign title.
    # The pill location is defined independently for EACH original background.
    # Re-anchor also when an existing scene from older Beta revisions opens.
    x, y, width, height = _date_geometry(page, campaign)
    node.transform.x, node.transform.y = x, y
    node.transform.width, node.transform.height = width, height
    node.style.update({"font_family": "Impact", "font_size": 13,
                       "font_size_unit": "pt", "font_weight": 700,
                       "fit_inside_box": True, "single_line": True,
                       "nowrap": True, "align": "center", "v_align": "center"})
    node.metadata["campaign_date_calibrated"] = True
    node.metadata["campaign_date_box_version"] = 58
    node.style["min_font_size"] = 8
    node.text = displayed
    node.metadata["campaign_id"] = campaign
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
        target = (campaign_footer_theme(session.document, session.page, theme)
                  if theme in CAMPAIGNS else THEMES[theme])
    elif re.fullmatch(r"#[0-9a-f]{6}", theme):
        target = theme.upper()
    else:
        raise ValueError("Escolha Azul, Terça Verde ou uma cor hexadecimal #RRGGBB.")
    page = session.page
    # Slot Único uses its certified older royal blue, unlike Multi/Individual.
    palette = {value.upper() for value in THEMES.values()}
    palette.update(LEGACY_THEME_COLORS)
    page_color = str(page.metadata.get("slot_theme_color") or "").upper()
    if re.fullmatch(r"#[0-9A-F]{6}", page_color):
        palette.add(page_color)
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
            page.metadata["slot_theme_color"] = target
        recolored = set()
        for slot in slots:
            # Only the generic page-sized backing is transparent. Source
            # white panels are part of the artwork, not campaign background.
            for nid in page.descendants(str(slot.metadata.get("root_node_id") or "")):
                plate = page.node(nid)
                if plate is not None:
                    if plate.metadata.get("item_slot_background"):
                        plate.visible = False
                    elif (plate.metadata.get("item_slot_name_backdrop")
                          or plate.metadata.get("limpeza_blue_role") == "white_panel"):
                        plate.visible = True
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
            # Campaign artwork fades to a pale area behind the Multi ribbon.
            # White names disappear there, especially with no product photo.
            if theme in CAMPAIGNS and slot.metadata.get("preset_id") == "multi-cell-beta44":
                name_node = page.node(str(slot.node_by_role.get("name") or ""))
                if name_node is not None:
                    name_node.style["color"] = target
                    recolored.add(name_node.id)
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
                if node.name == "Fundo branco da faixa":
                    node.visible = False
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
