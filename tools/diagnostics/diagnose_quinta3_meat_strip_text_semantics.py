from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

REQUESTED_SHA = "21dda44fe758a2899b4c15ffa041b2e0f6ff6d33"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
PAGE_WIDTH = 1080.0
PAGE_HEIGHT = 1350.0
RASTER_SCALE = 2.0
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}

ROLE_IDS = {
    "costela": {"name": 49, "currency": 45, "integer": 47, "decimal": 48, "unit": 46},
    "pernil": {"name": 38, "currency": 33, "integer": 36, "decimal": 37, "unit": 35},
    "musculo": {"name": 41, "currency": 39, "integer": 26, "decimal": 27, "unit": 40},
    "moela": {"name": 44, "currency": 42, "integer": 31, "decimal": 43, "unit": 34},
}
ROLE_ORDER = ("name", "currency", "integer", "decimal", "unit")
PROFILE_ORDER = ("costela", "pernil", "musculo", "moela")
PRIMARY_METRIC_ROLES = {"name", "currency", "decimal"}
CONTROL_ROLES = {"integer", "unit"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(source_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source_root), *args], text=True).strip()


def rect_values(rect) -> list[float]:
    rect = rect.normalized()
    return [float(rect.x), float(rect.y), float(rect.width), float(rect.height)]


def clean_meta(meta: dict) -> dict:
    keep = {}
    for key, value in meta.items():
        lower = str(key).casefold()
        if any(token in lower for token in ("paragraph", "empty", "newline", "pptx_text", "text_content", "autofit", "wrap")):
            try:
                json.dumps(value)
                keep[str(key)] = copy.deepcopy(value)
            except TypeError:
                keep[str(key)] = repr(value)
    return keep


def runtime_snapshot(node) -> dict:
    text = str(node.text or "")
    return {
        "NODE_ID": str(node.id),
        "SOURCE_SHAPE_ID": str(node.metadata.get("source_shape_id") or ""),
        "TEXT_REPR": repr(text),
        "TEXT": text,
        "PARAGRAPH_COUNT_FROM_TEXT": text.count("\n") + 1,
        "NEWLINE_COUNT": text.count("\n"),
        "PPTX_TEXT_CONTENT": copy.deepcopy(node.metadata.get("pptx_text_content")),
        "EMPTY_PARAGRAPH_METADATA": clean_meta(node.metadata),
        "NOWRAP": bool(node.style.get("nowrap")),
        "PPTX_AUTO_FIT": str(node.style.get("pptx_auto_fit") or ""),
        "V_ALIGN": str(node.style.get("v_align") or node.style.get("vertical_align") or ""),
        "RECT": rect_values(node.rect),
    }


def _source_text_from_paragraph(paragraph) -> tuple[str, int]:
    parts: list[str] = []
    br_count = 0
    for child in list(paragraph):
        local = child.tag.rsplit("}", 1)[-1]
        if local in {"r", "fld"}:
            t = child.find("./a:t", NS)
            parts.append("" if t is None else (t.text or ""))
        elif local == "br":
            parts.append("\n")
            br_count += 1
    return "".join(parts), br_count


def _run_style(paragraph) -> dict:
    records = []
    for run in paragraph.findall("./a:r", NS):
        rpr = run.find("./a:rPr", NS)
        t = run.find("./a:t", NS)
        if rpr is None:
            continue
        latin = rpr.find("./a:latin", NS)
        records.append(
            {
                "text": "" if t is None else (t.text or ""),
                "font": "" if latin is None else str(latin.get("typeface") or ""),
                "size_pt": (float(rpr.get("sz")) / 100.0) if rpr.get("sz") else None,
                "letter_spacing_pt": (float(rpr.get("spc")) / 100.0) if rpr.get("spc") else 0.0,
                "bold": str(rpr.get("b") or "").casefold() in {"1", "true"},
                "italic": str(rpr.get("i") or "").casefold() in {"1", "true"},
            }
        )
    if records:
        return {"runs": records, "primary": records[0]}
    end = paragraph.find("./a:endParaRPr", NS)
    if end is None:
        return {"runs": [], "primary": {}}
    latin = end.find("./a:latin", NS)
    primary = {
        "text": "",
        "font": "" if latin is None else str(latin.get("typeface") or ""),
        "size_pt": (float(end.get("sz")) / 100.0) if end.get("sz") else None,
        "letter_spacing_pt": (float(end.get("spc")) / 100.0) if end.get("spc") else 0.0,
        "bold": str(end.get("b") or "").casefold() in {"1", "true"},
        "italic": str(end.get("i") or "").casefold() in {"1", "true"},
    }
    return {"runs": [], "primary": primary}


def extract_source_semantics(pptx: Path) -> tuple[list[float], dict[str, dict[str, dict]], dict]:
    with zipfile.ZipFile(pptx) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        size = presentation.find(".//p:sldSz", NS)
        if size is None:
            raise RuntimeError("p:sldSz missing")
        slide_emu = [float(size.get("cx") or 0), float(size.get("cy") or 0)]
        if slide_emu != [10287000.0, 12852400.0]:
            raise RuntimeError(f"Unexpected exact source page: {slide_emu}")
        slide = ET.fromstring(archive.read("ppt/slides/slide1.xml"))

    by_id = {}
    for shape in slide.findall(".//p:sp", NS):
        c_nv = shape.find("./p:nvSpPr/p:cNvPr", NS)
        if c_nv is not None:
            by_id[str(c_nv.get("id") or "")] = shape

    result: dict[str, dict[str, dict]] = {}
    for profile_id, roles in ROLE_IDS.items():
        result[profile_id] = {}
        for role, shape_id in roles.items():
            shape = by_id.get(str(shape_id))
            if shape is None:
                raise RuntimeError(f"source shape {shape_id} missing")
            c_nv = shape.find("./p:nvSpPr/p:cNvPr", NS)
            body = shape.find("./p:txBody/a:bodyPr", NS)
            if body is None:
                raise RuntimeError(f"{profile_id}/{role}: bodyPr missing")
            paragraphs = shape.findall("./p:txBody/a:p", NS)
            p_rows = []
            total_br = 0
            total_runs = 0
            for index, paragraph in enumerate(paragraphs):
                text, br_count = _source_text_from_paragraph(paragraph)
                ppr = paragraph.find("./a:pPr", NS)
                style = _run_style(paragraph)
                total_br += br_count
                total_runs += len(paragraph.findall("./a:r", NS))
                p_rows.append(
                    {
                        "index": index,
                        "text": text,
                        "text_repr": repr(text),
                        "empty": text == "",
                        "break_count": br_count,
                        "run_count": len(paragraph.findall("./a:r", NS)),
                        "alignment": "" if ppr is None else str(ppr.get("algn") or ""),
                        "style": style,
                    }
                )
            paragraph_text = "\n".join(row["text"] for row in p_rows)
            raw_wrap = body.get("wrap")
            effective_wrap = "square" if raw_wrap is None else str(raw_wrap)
            auto_children = [item.tag.rsplit("}", 1)[-1] for item in list(body)]
            all_styles = [row["style"]["primary"] for row in p_rows if row["style"]["primary"]]
            primary_style = all_styles[0] if all_styles else {}
            result[profile_id][role] = {
                "SHAPE_ID": shape_id,
                "SHAPE_NAME": "" if c_nv is None else str(c_nv.get("name") or ""),
                "TEXT": paragraph_text,
                "TEXT_REPR": repr(paragraph_text),
                "BODYPR_XML": ET.tostring(body, encoding="unicode"),
                "SOURCE_WRAP_RAW": raw_wrap,
                "SOURCE_WRAP_EFFECTIVE": effective_wrap,
                "ANCHOR": str(body.get("anchor") or ""),
                "VERT": str(body.get("vert") or ""),
                "LINS": body.get("lIns"),
                "RINS": body.get("rIns"),
                "TINS": body.get("tIns"),
                "BINS": body.get("bIns"),
                "SPAUTOFIT": "spAutoFit" in auto_children,
                "NORMAUTOFIT": "normAutofit" in auto_children,
                "NOAUTOFIT": "noAutofit" in auto_children,
                "AUTOFIT_CHILDREN": auto_children,
                "PARAGRAPH_COUNT": len(p_rows),
                "EMPTY_PARAGRAPH_COUNT": sum(1 for row in p_rows if row["empty"]),
                "BREAK_COUNT": total_br,
                "RUN_COUNT": total_runs,
                "PARAGRAPHS": p_rows,
                "PARAGRAPH_ALIGNMENT": [row["alignment"] for row in p_rows],
                "FONT": primary_style.get("font"),
                "FONT_SIZE_PT": primary_style.get("size_pt"),
                "LETTER_SPACING_PT": primary_style.get("letter_spacing_pt"),
            }
    summary = {
        "SOURCE_PAGE_EMU": slide_emu,
        "WRAP_DEFAULT_RULE": "DrawingML bodyPr@wrap omitted => square",
        "TARGET_NODE_COUNT": sum(len(v) for v in ROLE_IDS.values()),
    }
    return slide_emu, result, summary


def source_text_for_runtime(source: dict) -> str:
    return str(source["TEXT"])


def apply_variant(document, slots, source_semantics, variant: str):
    from srstudio.graphics2.model import BindingRole

    role_binding = {
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }
    page = document.active_page
    for profile_id, slot in zip(PROFILE_ORDER, slots):
        for role, binding in role_binding.items():
            node = page.node(slot.node_by_role[binding.value])
            if node is None:
                raise RuntimeError(f"{profile_id}/{role}: runtime node missing")
            source = source_semantics[profile_id][role]
            if variant in {"source_wrap", "full_source"}:
                node.style["nowrap"] = str(source["SOURCE_WRAP_EFFECTIVE"]).casefold() == "none"
            if variant in {"source_paragraphs", "full_source"}:
                node.text = source_text_for_runtime(source)


def crop_strip(full_png: Path, strip_rect: list[float], reference_png: Path, output: Path):
    from PIL import Image

    image = Image.open(full_png).convert("RGB")
    reference = Image.open(reference_png).convert("RGB")
    left = int(math.floor(strip_rect[0] * RASTER_SCALE))
    top = int(math.floor(strip_rect[1] * RASTER_SCALE))
    crop = image.crop((left, top, left + reference.width, top + reference.height))
    crop.save(output)
    return crop, reference


def metric_crop_rect(source, strip_source_page_px, reference_size):
    x, y, w, h = source["SOURCE_RECT_PAGE_PX"]
    sx, sy, sw, sh = strip_source_page_px
    scale_x = reference_size[0] / sw
    scale_y = reference_size[1] / sh
    margin = 4
    left = max(0, int(math.floor((x - sx) * scale_x)) - margin)
    top = max(0, int(math.floor((y - sy) * scale_y)) - margin)
    right = min(reference_size[0], int(math.ceil((x + w - sx) * scale_x)) + margin)
    bottom = min(reference_size[1], int(math.ceil((y + h - sy) * scale_y)) + margin)
    return [left, top, right, bottom]


def diff_metrics(reference, candidate, box) -> dict:
    import numpy as np

    ref = np.asarray(reference.crop(tuple(box)), dtype=np.int16)
    cand = np.asarray(candidate.crop(tuple(box)), dtype=np.int16)
    if ref.shape != cand.shape:
        raise RuntimeError(f"metric crop mismatch {ref.shape} != {cand.shape}")
    delta = np.abs(ref - cand)
    changed = np.any(delta > 8, axis=2)
    return {
        "CHANGED_RATIO": float(changed.mean()) if changed.size else 0.0,
        "MAE": float(delta.mean()) if delta.size else 0.0,
        "CROP_BOX": box,
    }


def draw_text_probe(node, qt_renderer, QtCore, QtGui, out_path: Path) -> dict:
    from PIL import Image
    import numpy as np

    rect = node.rect.normalized()
    margin = 8.0
    width = max(16, int(math.ceil((rect.width + margin * 2) * RASTER_SCALE)))
    height = max(16, int(math.ceil((max(rect.height, 80.0) + margin * 2) * RASTER_SCALE)))
    image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtGui.QColor("#000000"))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    painter.scale(RASTER_SCALE, RASTER_SCALE)
    painter.translate(-rect.x + margin, -rect.y + margin)
    qt_renderer._draw_text(painter, node, QtCore, QtGui)
    painter.end()
    image.save(str(out_path), "PNG", 100)

    arr = np.asarray(Image.open(out_path).convert("RGB"))
    mask = np.max(arr, axis=2) > 32
    ys, xs = np.nonzero(mask)
    bbox = None if len(xs) == 0 else [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]

    line_bands = []
    if len(ys):
        active_rows = np.where(mask.any(axis=1))[0]
        start = prev = int(active_rows[0])
        for value in active_rows[1:]:
            value = int(value)
            if value > prev + 2:
                line_bands.append([start, prev + 1])
                start = value
            prev = value
        line_bands.append([start, prev + 1])

    style = node.style
    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
    base_size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    logical_px = base_size * (96.0 / 72.0) if unit in {"pt", "point", "points"} else base_size
    font = QtGui.QFont(family)
    font.setPixelSize(max(1, round(logical_px)))
    qt_renderer._set_font_weight(font, style.get("font_weight"), QtGui)
    if style.get("letter_spacing") not in (None, ""):
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))
    text = str(node.text or "")
    local_rect = QtCore.QRectF(0.0, 0.0, rect.width, rect.height)
    explicit = qt_renderer._explicit_multiline_layout(text, local_rect, style, font, QtCore, QtGui)
    shape = qt_renderer._pptx_shape_autofit_single_line_layout(text, local_rect, style, font, QtGui)
    if explicit is not None:
        baseline_positions = [float(item[2]) for item in explicit]
        layout_path = "explicit_multiline"
    elif shape is not None:
        baseline_positions = [float(shape[1])]
        layout_path = "shape_autofit_explicit_baseline"
    else:
        metrics = QtGui.QFontMetricsF(font)
        baseline_positions = [float(metrics.ascent())]
        layout_path = "qrect_native"

    return {
        "RENDERED_BBOX": bbox,
        "RENDERED_WIDTH": 0 if bbox is None else bbox[2] - bbox[0],
        "RENDERED_HEIGHT": 0 if bbox is None else bbox[3] - bbox[1],
        "LINE_COUNT": len(line_bands),
        "GLYPH_BOUNDS": bbox,
        "LINE_BANDS": line_bands,
        "BASELINE_POSITIONS_LOCAL": baseline_positions,
        "LAYOUT_PATH": layout_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    pptx = args.pptx.resolve()
    source_root = args.source_root.resolve()
    reference = args.reference.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    checked = git(source_root, "rev-parse", "HEAD")
    if checked != REQUESTED_SHA:
        raise RuntimeError(f"Exact SHA mismatch: {checked} != {REQUESTED_SHA}")
    actual_pptx = sha256(pptx)
    if actual_pptx != PPTX_SHA256:
        raise RuntimeError(f"PPTX SHA mismatch: {actual_pptx} != {PPTX_SHA256}")

    sys.path.insert(0, str(source_root / "src"))

    from PIL import Image
    from PySide6 import QtCore, QtGui
    from srstudio.graphics2 import qt_renderer
    from srstudio.graphics2.fonts import ensure_qgui_application, register_qt_document_fonts
    from srstudio.graphics2.import_bridge import GraphicsImportService
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.model import AssetRef, BindingRole, GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.qt_renderer import render_png
    from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID, MEAT_STRIP_FULL_CARD_PROFILES
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import strip_ownership_snapshot

    app = ensure_qgui_application()
    slide_emu, source_semantics, source_summary = extract_source_semantics(pptx)

    imported = GraphicsImportService().import_file(pptx, project_name="Meat Strip text semantics")
    document = GraphicsDocument(name="Meat Strip text semantics diagnostic")
    document.pages = [GraphicsPage(name="Página 1", width=PAGE_WIDTH, height=PAGE_HEIGHT, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    if isinstance(imported.document.metadata.get("embedded_fonts"), list):
        document.metadata["embedded_fonts"] = copy.deepcopy(imported.document.metadata["embedded_fonts"])
    legacy = imported.document.metadata.get("legacy_settings")
    if isinstance(legacy, dict) and isinstance(legacy.get("canva_embedded_fonts"), list):
        document.metadata["legacy_settings"] = {"canva_embedded_fonts": copy.deepcopy(legacy["canva_embedded_fonts"])}

    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)
    media_dir = out / "official-binding-media"
    media_dir.mkdir(exist_ok=True)
    assets = {}
    paths = {}
    with zipfile.ZipFile(pptx) as archive:
        for profile_id in PROFILE_ORDER:
            spec = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
            internal = str(spec["image_asset"]["internal_media"]).lstrip("/")
            raw = archive.read(internal)
            expected = str(spec["image_asset"]["sha256"])
            actual = hashlib.sha256(raw).hexdigest()
            if actual != expected:
                raise RuntimeError(f"{profile_id}: image SHA mismatch")
            local = media_dir / f"{profile_id}-{Path(internal).name}"
            local.write_bytes(raw)
            asset = AssetRef(kind="image", source=str(local), mime="image/png", sha256=actual, embedded=False)
            document.assets[asset.id] = asset
            assets[profile_id] = asset
            paths[profile_id] = local

    products = {
        "costela": {"id": "pptx-costela", "name": "COSTELA GAÚCHA", "price": "24.86", "unit": "KG"},
        "pernil": {"id": "pptx-pernil", "name": "PERNIL SUINO S/ OSSO", "price": "18.74", "unit": "KG"},
        "musculo": {"id": "pptx-musculo", "name": "MÚSCULO BOVINO", "price": "32.73", "unit": "KG"},
        "moela": {"id": "pptx-moela", "name": "MOELA DE FRANGO", "price": "16.72", "unit": "KG"},
    }
    role_binding = {
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }

    slots = []
    before_after = []
    for profile_id in PROFILE_ORDER:
        added = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        if not added.ok or not added.changed:
            raise RuntimeError(added.to_dict())
        slot = session.page.slots[added.payload["slot_id"]]
        before = {}
        for role, binding in role_binding.items():
            node = session.page.node(slot.node_by_role[binding.value])
            if node is None:
                raise RuntimeError(f"{profile_id}/{role}: before-bind node missing")
            before[role] = runtime_snapshot(node)

        product = dict(products[profile_id])
        product.update(
            {
                "quinta3_supervised_profile": profile_id,
                "image_asset_id": assets[profile_id].id,
                "image_path": str(paths[profile_id]),
            }
        )
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        if not bound.ok or not bound.changed:
            raise RuntimeError(bound.to_dict())

        after = {}
        for role, binding in role_binding.items():
            node = session.page.node(slot.node_by_role[binding.value])
            if node is None:
                raise RuntimeError(f"{profile_id}/{role}: after-bind node missing")
            after[role] = runtime_snapshot(node)
        before_after.append({"PROFILE": profile_id, "BEFORE": before, "AFTER": after})
        slots.append(slot)

    strip_ids = {str(slot.metadata.get("meat_strip_root_id") or "") for slot in slots}
    if len(strip_ids) != 1:
        raise RuntimeError(f"Expected one MeatStripRoot: {strip_ids}")
    strip_id = next(iter(strip_ids))
    strip = session.page.node(strip_id)
    if strip is None:
        raise RuntimeError("MeatStripRoot missing")
    if len(strip_ownership_snapshot(session.page, strip_id).get("cell_root_ids") or []) != 4:
        raise RuntimeError("Ownership regression in diagnostic setup")

    registration = register_qt_document_fonts(document)
    app.processEvents()
    anton = QtGui.QFontInfo(QtGui.QFont("Anton"))
    if not anton.exactMatch() or str(anton.family()).casefold() != "anton":
        raise RuntimeError("Anton exactMatch gate failed")

    source_strip_emu = [
        min(float(MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"][0]) for p in PROFILE_ORDER),
        min(float(MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"][1]) for p in PROFILE_ORDER),
        0.0,
        0.0,
    ]
    right = max(float(MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"][0]) + float(MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"][2]) for p in PROFILE_ORDER)
    bottom = max(float(MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"][1]) + float(MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"][3]) for p in PROFILE_ORDER)
    source_strip_emu[2] = right - source_strip_emu[0]
    source_strip_emu[3] = bottom - source_strip_emu[1]
    strip_source_page_px = [
        source_strip_emu[0] / slide_emu[0] * PAGE_WIDTH,
        source_strip_emu[1] / slide_emu[1] * PAGE_HEIGHT,
        source_strip_emu[2] / slide_emu[0] * PAGE_WIDTH,
        source_strip_emu[3] / slide_emu[1] * PAGE_HEIGHT,
    ]

    with zipfile.ZipFile(pptx) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
    by_id = {}
    for candidate in slide.findall(".//p:sp", NS):
        c_nv = candidate.find("./p:nvSpPr/p:cNvPr", NS)
        if c_nv is not None:
            by_id[str(c_nv.get("id") or "")] = candidate
    for profile_id in PROFILE_ORDER:
        for role in ROLE_ORDER:
            source_id = source_semantics[profile_id][role]["SHAPE_ID"]
            shape = by_id.get(str(source_id))
            if shape is None:
                raise RuntimeError(f"shape {source_id} not found for source rect")
            xfrm = shape.find("./p:spPr/a:xfrm", NS)
            off = xfrm.find("./a:off", NS) if xfrm is not None else None
            ext = xfrm.find("./a:ext", NS) if xfrm is not None else None
            if off is None or ext is None:
                raise RuntimeError(f"shape {source_id}: xfrm incomplete")
            emu = [float(off.get("x") or 0), float(off.get("y") or 0), float(ext.get("cx") or 0), float(ext.get("cy") or 0)]
            source_semantics[profile_id][role]["SOURCE_RECT_EMU"] = emu
            source_semantics[profile_id][role]["SOURCE_RECT_PAGE_PX"] = [
                emu[0] / slide_emu[0] * PAGE_WIDTH,
                emu[1] / slide_emu[1] * PAGE_HEIGHT,
                emu[2] / slide_emu[0] * PAGE_WIDTH,
                emu[3] / slide_emu[1] * PAGE_HEIGHT,
            ]

    source_payload = {
        "SOURCE_SHA": REQUESTED_SHA,
        "PPTX_SHA256": PPTX_SHA256,
        **source_summary,
        "SOURCE_STRIP_PAGE_PX": strip_source_page_px,
        "NODES": source_semantics,
    }
    (out / "text-semantics-source.json").write_text(json.dumps(source_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "text-runtime-before-after-bind.json").write_text(json.dumps(before_after, ensure_ascii=False, indent=2), encoding="utf-8")

    variants = {
        "current": "text-variant-current.png",
        "source_wrap": "text-variant-source-wrap.png",
        "source_paragraphs": "text-variant-source-paragraphs.png",
        "full_source": "text-variant-full-source.png",
    }
    Image.open(reference).convert("RGB")
    all_metrics = []
    variant_summary = {}
    probe_dir = out / "probes"
    probe_dir.mkdir(exist_ok=True)
    crop_dir = out / "crops"
    crop_dir.mkdir(exist_ok=True)

    for variant, filename in variants.items():
        doc = copy.deepcopy(document)
        cloned_slots = [doc.active_page.slots[slot.id] for slot in slots]
        apply_variant(doc, cloned_slots, source_semantics, variant)
        full_path = out / f"_page-{variant}.png"
        report = render_png(doc, full_path, target_width=2160)
        if not report.ok or report.warnings:
            raise RuntimeError(f"{variant}: render failed/warnings={report.warnings}")
        strip_node = doc.active_page.node(strip_id)
        strip_crop, reference_crop = crop_strip(full_path, rect_values(strip_node.rect), reference, out / filename)

        role_mae = {}
        role_changed = {}
        for profile_id, cloned_slot in zip(PROFILE_ORDER, cloned_slots):
            for role, binding in role_binding.items():
                node = doc.active_page.node(cloned_slot.node_by_role[binding.value])
                source = source_semantics[profile_id][role]
                box = metric_crop_rect(source, strip_source_page_px, reference_crop.size)
                metrics = diff_metrics(reference_crop, strip_crop, box)
                probe = draw_text_probe(node, qt_renderer, QtCore, QtGui, probe_dir / f"{variant}-{profile_id}-{role}.png")
                row = {
                    "VARIANT": variant,
                    "PROFILE": profile_id,
                    "ROLE": role,
                    "SOURCE_WRAP_RAW": source["SOURCE_WRAP_RAW"],
                    "SOURCE_WRAP_EFFECTIVE": source["SOURCE_WRAP_EFFECTIVE"],
                    "RUNTIME_NOWRAP": bool(node.style.get("nowrap")),
                    "TEXT_REPR": repr(str(node.text or "")),
                    **metrics,
                    **probe,
                }
                all_metrics.append(row)
                role_mae.setdefault(role, []).append(metrics["MAE"])
                role_changed.setdefault(role, []).append(metrics["CHANGED_RATIO"])
                if role in PRIMARY_METRIC_ROLES:
                    reference_crop.crop(tuple(box)).save(crop_dir / f"reference-{profile_id}-{role}.png")
                    strip_crop.crop(tuple(box)).save(crop_dir / f"{variant}-{profile_id}-{role}.png")
        variant_summary[variant] = {
            "ROLE_MAE": {role: sum(values) / len(values) for role, values in role_mae.items()},
            "ROLE_CHANGED_RATIO": {role: sum(values) / len(values) for role, values in role_changed.items()},
            "PRIMARY_MAE": sum(v for role, values in role_mae.items() if role in PRIMARY_METRIC_ROLES for v in values)
            / sum(len(values) for role, values in role_mae.items() if role in PRIMARY_METRIC_ROLES),
            "CONTROL_MAE": sum(v for role, values in role_mae.items() if role in CONTROL_ROLES for v in values)
            / sum(len(values) for role, values in role_mae.items() if role in CONTROL_ROLES),
        }

    baseline_metrics = {}
    for baseline_variant, semantic_variant in (("current_qrect", "current"), ("full_source_qrect", "full_source")):
        doc = copy.deepcopy(document)
        cloned_slots = [doc.active_page.slots[slot.id] for slot in slots]
        apply_variant(doc, cloned_slots, source_semantics, semantic_variant)
        original_helper = qt_renderer._pptx_shape_autofit_single_line_layout
        qt_renderer._pptx_shape_autofit_single_line_layout = lambda *a, **k: None
        try:
            full_path = out / f"_page-{baseline_variant}.png"
            report = render_png(doc, full_path, target_width=2160)
        finally:
            qt_renderer._pptx_shape_autofit_single_line_layout = original_helper
        if not report.ok or report.warnings:
            raise RuntimeError(f"{baseline_variant}: render failed/warnings={report.warnings}")
        strip_crop, reference_crop = crop_strip(full_path, rect_values(doc.active_page.node(strip_id).rect), reference, out / f"text-variant-{baseline_variant}.png")
        role_mae = {}
        for profile_id, cloned_slot in zip(PROFILE_ORDER, cloned_slots):
            for role, binding in role_binding.items():
                source = source_semantics[profile_id][role]
                box = metric_crop_rect(source, strip_source_page_px, reference_crop.size)
                metrics = diff_metrics(reference_crop, strip_crop, box)
                role_mae.setdefault(role, []).append(metrics["MAE"])
        baseline_metrics[baseline_variant] = {
            "ROLE_MAE": {role: sum(values) / len(values) for role, values in role_mae.items()},
            "PRIMARY_MAE": sum(v for role, values in role_mae.items() if role in PRIMARY_METRIC_ROLES for v in values)
            / sum(len(values) for role, values in role_mae.items() if role in PRIMARY_METRIC_ROLES),
            "CONTROL_MAE": sum(v for role, values in role_mae.items() if role in CONTROL_ROLES for v in values)
            / sum(len(values) for role, values in role_mae.items() if role in CONTROL_ROLES),
        }

    best = min(variant_summary, key=lambda key: variant_summary[key]["PRIMARY_MAE"])
    summary = {
        "SOURCE_SHA": REQUESTED_SHA,
        "PPTX_SHA256": PPTX_SHA256,
        "ANTON_REGISTERED_FAMILIES": list(registration.families),
        "ANTON_EXACT_MATCH": True,
        "VARIANTS": variant_summary,
        "BASELINE_AXIS": baseline_metrics,
        "BEST_VARIANT": best,
        "BEST_VARIANT_METRICS": variant_summary[best],
    }
    (out / "text-variant-metrics.json").write_text(json.dumps(all_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "text-semantics-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"SOURCE_SHA={REQUESTED_SHA}")
    print(f"PPTX_SHA={PPTX_SHA256}")
    print(f"BEST_VARIANT={best}")
    print(f"BEST_PRIMARY_MAE={variant_summary[best]['PRIMARY_MAE']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
