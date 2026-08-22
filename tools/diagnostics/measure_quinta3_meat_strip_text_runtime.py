from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

REQUESTED_SHA = "c69dd1b933e93e0928c4f299cc53ca771b22b4c2"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
PAGE_WIDTH = 1080.0
PAGE_HEIGHT = 1350.0
PT_TO_PX = 96.0 / 72.0
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}
ROLE_IDS = {
    "costela": {"name": 49, "currency": 45, "integer": 47, "decimal": 48, "unit": 46},
    "pernil": {"name": 38, "currency": 33, "integer": 36, "decimal": 37, "unit": 35},
    "musculo": {"name": 41, "currency": 39, "integer": 26, "decimal": 27, "unit": 40},
    "moela": {"name": 44, "currency": 42, "integer": 31, "decimal": 43, "unit": 34},
}


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


def qrect_values(rect) -> list[float]:
    return [float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height())]


def _source_contracts(pptx: Path) -> tuple[list[float], dict[str, dict[str, dict]]]:
    with zipfile.ZipFile(pptx) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        slide_size = presentation.find(".//p:sldSz", NS)
        if slide_size is None:
            raise RuntimeError("p:sldSz missing")
        slide_emu = [float(slide_size.get("cx") or 0), float(slide_size.get("cy") or 0)]
        slide = ET.fromstring(archive.read("ppt/slides/slide1.xml"))

    by_id = {}
    for shape in slide.findall(".//p:sp", NS):
        c_nv = shape.find("./p:nvSpPr/p:cNvPr", NS)
        if c_nv is None:
            continue
        by_id[str(c_nv.get("id") or "")] = shape

    result: dict[str, dict[str, dict]] = {}
    for profile_id, roles in ROLE_IDS.items():
        result[profile_id] = {}
        for role, shape_id in roles.items():
            shape = by_id.get(str(shape_id))
            if shape is None:
                raise RuntimeError(f"source shape {shape_id} missing")
            xfrm = shape.find("./p:spPr/a:xfrm", NS)
            off = xfrm.find("./a:off", NS) if xfrm is not None else None
            ext = xfrm.find("./a:ext", NS) if xfrm is not None else None
            body = shape.find("./p:txBody/a:bodyPr", NS)
            p_pr = shape.find("./p:txBody/a:p/a:pPr", NS)
            r_pr = shape.find("./p:txBody/a:p/a:r/a:rPr", NS)
            if r_pr is None:
                r_pr = shape.find("./p:txBody/a:p/a:endParaRPr", NS)
            latin = r_pr.find("./a:latin", NS) if r_pr is not None else None
            if any(item is None for item in (off, ext, body, r_pr, latin)):
                raise RuntimeError(f"source text contract incomplete for {profile_id}/{role}")
            emu = [float(off.get("x") or 0), float(off.get("y") or 0), float(ext.get("cx") or 0), float(ext.get("cy") or 0)]
            source_rect = [
                emu[0] / slide_emu[0] * PAGE_WIDTH,
                emu[1] / slide_emu[1] * PAGE_HEIGHT,
                emu[2] / slide_emu[0] * PAGE_WIDTH,
                emu[3] / slide_emu[1] * PAGE_HEIGHT,
            ]
            size_pt = float(r_pr.get("sz") or 0) / 100.0
            spacing_pt = float(r_pr.get("spc") or 0) / 100.0
            result[profile_id][role] = {
                "SOURCE_SHAPE_ID": shape_id,
                "TEXT": "".join(item.text or "" for item in shape.findall(".//a:t", NS)),
                "SOURCE_RECT_EMU": emu,
                "SOURCE_RECT_PAGE_PX": source_rect,
                "SOURCE_FONT_FAMILY": str(latin.get("typeface") or ""),
                "SOURCE_FONT_SIZE_PT": size_pt,
                "SOURCE_FONT_SIZE_PX_96DPI": size_pt * PT_TO_PX,
                "SOURCE_WEIGHT": 700 if str(r_pr.get("b") or "").lower() in {"1", "true"} else 400,
                "SOURCE_LETTER_SPACING_PT": spacing_pt,
                "SOURCE_LETTER_SPACING_PX_96DPI": spacing_pt * PT_TO_PX,
                "SOURCE_ALIGN": str((p_pr.get("algn") if p_pr is not None else "") or "left"),
                "SOURCE_V_ALIGN": str(body.get("anchor") or "t"),
                "SOURCE_TEXT_INSETS_EMU": {
                    "left": float(body.get("lIns") or 0),
                    "top": float(body.get("tIns") or 0),
                    "right": float(body.get("rIns") or 0),
                    "bottom": float(body.get("bIns") or 0),
                },
                "SOURCE_AUTOFIT": [item.tag.rsplit("}", 1)[-1] for item in list(body)],
            }
    return slide_emu, result


def _font_metrics(font, text, QtGui) -> dict:
    metrics = QtGui.QFontMetricsF(font)
    bounds = metrics.boundingRect(text)
    tight = metrics.tightBoundingRect(text)
    return {
        "pixelSize": int(font.pixelSize()),
        "pointSizeF": float(font.pointSizeF()),
        "ascent": float(metrics.ascent()),
        "descent": float(metrics.descent()),
        "height": float(metrics.height()),
        "leading": float(metrics.leading()),
        "capHeight": float(metrics.capHeight()),
        "xHeight": float(metrics.xHeight()),
        "horizontalAdvance": float(metrics.horizontalAdvance(text)),
        "spaceAdvance": float(metrics.horizontalAdvance(" ")),
        "boundingRect": qrect_values(bounds),
        "tightBoundingRect": qrect_values(tight),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    pptx = args.pptx.resolve()
    source_root = args.source_root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    checked = git(source_root, "rev-parse", "HEAD")
    if checked != REQUESTED_SHA:
        raise RuntimeError(f"Exact SHA mismatch: {checked} != {REQUESTED_SHA}")
    actual_pptx_sha = sha256(pptx)
    if actual_pptx_sha != PPTX_SHA256:
        raise RuntimeError(f"PPTX SHA mismatch: {actual_pptx_sha} != {PPTX_SHA256}")

    sys.path.insert(0, str(source_root / "src"))

    from PySide6 import QtGui
    from PySide6.QtGui import QFont, QFontInfo, QImage

    from srstudio.graphics2.fonts import ensure_qgui_application, register_qt_document_fonts
    from srstudio.graphics2.import_bridge import GraphicsImportService
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.model import AssetRef, BindingRole, GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.qt_renderer import _set_font_weight, _should_fit_text, render_png
    from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID, MEAT_STRIP_FULL_CARD_PROFILES
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER

    app = ensure_qgui_application()
    imported = GraphicsImportService().import_file(pptx, project_name="Meat Strip text metric import")
    imported_doc = imported.document

    document = GraphicsDocument(name="Meat Strip text metrics")
    document.pages = [GraphicsPage(name="Página 1", width=PAGE_WIDTH, height=PAGE_HEIGHT, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    if isinstance(imported_doc.metadata.get("embedded_fonts"), list):
        document.metadata["embedded_fonts"] = copy.deepcopy(imported_doc.metadata["embedded_fonts"])
    legacy = imported_doc.metadata.get("legacy_settings")
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
            actual = hashlib.sha256(raw).hexdigest()
            expected = str(spec["image_asset"]["sha256"])
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
    slots = []
    for profile_id in PROFILE_ORDER:
        added = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        if not added.ok or not added.changed:
            raise RuntimeError(added.to_dict())
        slot = session.page.slots[added.payload["slot_id"]]
        product = dict(products[profile_id])
        product.update({"quinta3_supervised_profile": profile_id, "image_asset_id": assets[profile_id].id, "image_path": str(paths[profile_id])})
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        if not bound.ok or not bound.changed:
            raise RuntimeError(bound.to_dict())
        slots.append(slot)

    registration = register_qt_document_fonts(document)
    app.processEvents()
    anton_info = QFontInfo(QFont("Anton"))
    render = render_png(document, out / "meat-strip-text-current-g2-page.png", target_width=2160)
    if not render.ok:
        raise RuntimeError("clean production render failed")

    slide_emu, source_contracts = _source_contracts(pptx)
    role_binding = {
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }
    rows = []
    image_checks = []
    for profile_id, slot in zip(PROFILE_ORDER, slots):
        image_node = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
        asset = document.assets.get(image_node.asset_id) if image_node is not None else None
        qimage = QImage(str(asset.source)) if asset is not None else QImage()
        image_checks.append({"profile": profile_id, "binding": bool(image_node and asset), "decode": not qimage.isNull()})
        for role, binding in role_binding.items():
            node = session.page.node(slot.node_by_role[binding.value])
            if node is None:
                raise RuntimeError(f"{profile_id}/{role}: runtime node missing")
            style = node.style
            source = source_contracts[profile_id][role]
            family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
            size_pt = float(style.get("font_size") or 20.0)
            unit = str(style.get("font_size_unit") or "pt").lower()
            logical_px = size_pt * PT_TO_PX if unit in {"pt", "point", "points"} else size_pt
            font = QFont(family)
            font.setPixelSize(max(1, round(logical_px)))
            _set_font_weight(font, style.get("font_weight"), QtGui)
            font.setItalic(bool(style.get("italic")))
            if style.get("letter_spacing") not in (None, ""):
                font.setLetterSpacing(QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))

            no_spacing = QFont(font)
            no_spacing.setLetterSpacing(QFont.AbsoluteSpacing, 0.0)
            fractional = QFont(family)
            fractional.setPointSizeF(size_pt)
            _set_font_weight(fractional, style.get("font_weight"), QtGui)
            fractional.setItalic(bool(style.get("italic")))
            if style.get("letter_spacing") not in (None, ""):
                fractional.setLetterSpacing(QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))

            runtime_rect = rect_values(node.rect)
            source_rect = source["SOURCE_RECT_PAGE_PX"]
            rows.append({
                "PROFILE": profile_id.upper(),
                "ROLE": role.upper(),
                **source,
                "RUNTIME_RECT": runtime_rect,
                "RUNTIME_TO_SOURCE_RECT_WIDTH": runtime_rect[2] / max(source_rect[2], 1e-9),
                "RUNTIME_TO_SOURCE_RECT_HEIGHT": runtime_rect[3] / max(source_rect[3], 1e-9),
                "RUNTIME_FONT_FAMILY_REQUESTED": family,
                "RUNTIME_FONT_FAMILY_RESOLVED": str(QFontInfo(font).family() or ""),
                "RUNTIME_FONT_EXACT_MATCH": bool(QFontInfo(font).exactMatch()),
                "RUNTIME_FONT_SIZE_PT_STYLE": size_pt,
                "RUNTIME_FONT_SIZE_LOGICAL_PX_FLOAT": logical_px,
                "RUNTIME_FONT_PIXEL_SIZE_APPLIED": int(font.pixelSize()),
                "RUNTIME_FONT_WEIGHT": int(font.weight()),
                "RUNTIME_LETTER_SPACING_PT": float(style.get("letter_spacing_pt") or 0.0),
                "RUNTIME_LETTER_SPACING_PX": float(style.get("letter_spacing") or 0.0),
                "RUNTIME_ALIGN": str(style.get("align") or ""),
                "RUNTIME_V_ALIGN": str(style.get("v_align") or style.get("vertical_align") or ""),
                "RUNTIME_TEXT_INSETS": copy.deepcopy(style.get("text_insets") or {}),
                "RUNTIME_PPTX_AUTO_FIT": str(style.get("pptx_auto_fit") or ""),
                "RUNTIME_FIT_INSIDE_BOX": bool(style.get("fit_inside_box")),
                "RUNTIME_SEMANTIC_FIT_POLICY": str(style.get("semantic_fit_policy") or ""),
                "RUNTIME_SHOULD_FIT": bool(_should_fit_text(style)),
                "CURRENT_QFONT_METRICS": _font_metrics(font, str(node.text or ""), QtGui),
                "NO_SPACING_QFONT_METRICS": _font_metrics(no_spacing, str(node.text or ""), QtGui),
                "FRACTIONAL_POINT_QFONT_METRICS": _font_metrics(fractional, str(node.text or ""), QtGui),
            })

    strip_ids = {str(slot.metadata.get("meat_strip_root_id") or "") for slot in slots}
    strip = session.page.node(next(iter(strip_ids))) if len(strip_ids) == 1 else None
    payload = {
        "REQUESTED_SHA": checked,
        "PPTX_SHA256": actual_pptx_sha,
        "PPTX_SLIDE_SIZE_EMU": slide_emu,
        "PAGE_SIZE": [PAGE_WIDTH, PAGE_HEIGHT],
        "ANTON_REGISTERED_FAMILIES": list(registration.families),
        "ANTON_RESOLVED": str(anton_info.family() or ""),
        "ANTON_EXACT_MATCH": bool(anton_info.exactMatch()),
        "RUNTIME_STRIP_RECT": rect_values(strip.rect) if strip is not None else [],
        "OUT_OF_BOUNDS": bool(strip is None or strip.rect.x < 0 or strip.rect.y < 0 or strip.rect.right > PAGE_WIDTH or strip.rect.bottom > PAGE_HEIGHT),
        "IMAGE_CHECKS": image_checks,
        "RENDER_WARNINGS": [getattr(item, "code", "") for item in render.warnings],
        "ROWS": rows,
    }
    target = out / "meat-strip-text-runtime-metrics.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PPTX_SLIDE_SIZE_EMU={slide_emu[0]}x{slide_emu[1]}")
    print(f"ANTON_RESOLVED={payload['ANTON_RESOLVED']}")
    print(f"ANTON_EXACT_MATCH={str(payload['ANTON_EXACT_MATCH']).lower()}")
    print(f"RUNTIME_STRIP_RECT={payload['RUNTIME_STRIP_RECT']}")
    print(f"OUT_OF_BOUNDS={str(payload['OUT_OF_BOUNDS']).lower()}")
    print(f"IMAGES_OK={str(all(item['binding'] and item['decode'] for item in image_checks)).lower()}")
    print(f"RENDER_WARNINGS={payload['RENDER_WARNINGS']}")
    for row in rows:
        m = row["CURRENT_QFONT_METRICS"]
        print(
            f"{row['PROFILE']} {row['ROLE']} "
            f"sourceBox={row['SOURCE_RECT_PAGE_PX'][2]:.6f}x{row['SOURCE_RECT_PAGE_PX'][3]:.6f} "
            f"runtimeBox={row['RUNTIME_RECT'][2]:.6f}x{row['RUNTIME_RECT'][3]:.6f} "
            f"pt={row['RUNTIME_FONT_SIZE_PT_STYLE']:.2f} pxFloat={row['RUNTIME_FONT_SIZE_LOGICAL_PX_FLOAT']:.6f} "
            f"pxApplied={row['RUNTIME_FONT_PIXEL_SIZE_APPLIED']} spacingPx={row['RUNTIME_LETTER_SPACING_PX']:.6f} "
            f"advance={m['horizontalAdvance']:.6f} height={m['height']:.6f} ascent={m['ascent']:.6f} descent={m['descent']:.6f} "
            f"fit={row['RUNTIME_SHOULD_FIT']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
