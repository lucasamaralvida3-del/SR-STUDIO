from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": A, "p": P, "r": R}
AFTER_SHA = "2e706558132e8893377c0dd6772d55c6c9d3a739"
PPTX_SHA = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
ATTRS = ("latinLnBrk", "eaLnBrk", "hangingPunct", "algn", "rtl", "fontAlgn", "marL", "marR", "indent", "lvl")
STANDARD_DEFAULTS = {
    "latinLnBrk": True,
    "eaLnBrk": True,
    "hangingPunct": False,
    "algn": None,
    "rtl": None,
    "fontAlgn": None,
    "marL": 347663,
    "marR": None,
    "indent": -342900,
    "lvl": None,
}
OFFICE_DEFAULTS = {
    "latinLnBrk": False,
    "eaLnBrk": True,
    "hangingPunct": True,
    "algn": None,
    "rtl": None,
    "fontAlgn": None,
    "marL": 0,
    "marR": None,
    "indent": 0,
    "lvl": None,
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _boolish(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "on", "yes"}:
        return True
    if text in {"0", "false", "off", "no"}:
        return False
    return value


def _attr_value(name: str, value):
    if value is None:
        return None
    if name in {"latinLnBrk", "eaLnBrk", "hangingPunct", "rtl"}:
        return _boolish(value)
    if name in {"marL", "marR", "indent", "lvl"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def _resolve_rel(archive: zipfile.ZipFile, owner_path: str, rel_type_suffix: str) -> str | None:
    owner = Path(owner_path)
    rel_path = str(owner.parent / "_rels" / f"{owner.name}.rels").replace("\\", "/")
    if rel_path not in archive.namelist():
        return None
    root = ET.fromstring(archive.read(rel_path))
    for rel in list(root):
        if str(rel.get("Type") or "").endswith(rel_type_suffix):
            target = str(rel.get("Target") or "")
            base = owner.parent
            return str((base / target).as_posix()) if not target.startswith("/") else target.lstrip("/")
    return None


def _shape_by_id(root, shape_id: int):
    for shape in root.findall(".//p:sp", NS):
        c_nv = shape.find("./p:nvSpPr/p:cNvPr", NS)
        if c_nv is not None and int(c_nv.get("id") or -1) == int(shape_id):
            return shape
    return None


def _placeholder_key(shape):
    ph = shape.find("./p:nvSpPr/p:nvPr/p:ph", NS)
    if ph is None:
        return None
    return (ph.get("idx"), ph.get("type"))


def _matching_placeholder(root, key):
    if key is None:
        return None
    idx, typ = key
    candidates = []
    for shape in root.findall(".//p:sp", NS):
        ph = shape.find("./p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is None:
            continue
        candidates.append(shape)
        if idx is not None and ph.get("idx") == idx:
            return shape
    for shape in candidates:
        ph = shape.find("./p:nvSpPr/p:nvPr/p:ph", NS)
        if typ is not None and ph is not None and ph.get("type") == typ:
            return shape
    return None


def _paragraph_text(paragraph) -> str:
    parts = []
    for child in list(paragraph):
        local = _local(child.tag)
        if local in {"r", "fld"}:
            t = child.find("./a:t", NS)
            parts.append("" if t is None else str(t.text or ""))
        elif local == "br":
            parts.append("\n")
    return "".join(parts)


def _ppr_sources(shape, paragraph, label: str) -> list[tuple[str, object]]:
    result = []
    ppr = paragraph.find("./a:pPr", NS)
    if ppr is not None:
        result.append((f"{label}:paragraph", ppr))
    tx_body = shape.find("./p:txBody", NS)
    lst = tx_body.find("./a:lstStyle", NS) if tx_body is not None else None
    raw_lvl = ppr.get("lvl") if ppr is not None else None
    try:
        lvl = int(raw_lvl) if raw_lvl is not None else 0
    except ValueError:
        lvl = 0
    if lst is not None:
        level = lst.find(f"./a:lvl{max(1, min(9, lvl + 1))}pPr", NS)
        if level is not None:
            result.append((f"{label}:lvl{lvl + 1}pPr", level))
        default = lst.find("./a:defPPr", NS)
        if default is not None:
            result.append((f"{label}:defPPr", default))
    return result


def _resolve_attr(name: str, sources: list[tuple[str, object]]) -> dict:
    inherited_value = None
    inherited_source = None
    raw_value = None
    raw_xml = None
    for index, (source_name, elem) in enumerate(sources):
        if index == 0 and source_name.endswith(":paragraph"):
            raw_value = _attr_value(name, elem.get(name))
            raw_xml = ET.tostring(elem, encoding="unicode")
        if elem.get(name) is not None:
            value = _attr_value(name, elem.get(name))
            if index == 0 and source_name.endswith(":paragraph"):
                inherited_value = None
                inherited_source = None
            else:
                inherited_value = value
                inherited_source = source_name
            final = value
            final_source = source_name
            break
    else:
        final = None
        final_source = None
    standard_default = STANDARD_DEFAULTS.get(name)
    office_default = OFFICE_DEFAULTS.get(name)
    standard_effective = final if final is not None else standard_default
    office_effective = final if final is not None else office_default
    return {
        "RAW_PARAGRAPH_VALUE": raw_value,
        "RAW_PPR_XML": raw_xml,
        "INHERITED_VALUE": inherited_value,
        "INHERITED_SOURCE": inherited_source,
        "STANDARD_DEFAULT": standard_default,
        "OFFICE_DEFAULT": office_default,
        "STANDARD_EFFECTIVE": standard_effective,
        "FINAL_OFFICE_EFFECTIVE": office_effective,
        "EFFECTIVE_SOURCE": final_source or "default",
    }


def _script_name(ch: str, QtCore) -> str:
    try:
        value = QtCore.QChar(ch).script()
        return str(value).split(".")[-1]
    except Exception:
        name = unicodedata.name(ch, "UNKNOWN")
        return "Latin" if "LATIN" in name else "Unknown"


def _is_latin_letter(ch: str, QtCore) -> bool:
    if not ch.isalpha():
        return False
    script = _script_name(ch, QtCore).lower()
    return "latin" in script or "LATIN" in unicodedata.name(ch, "")


def token_class(text: str, QtCore) -> str:
    value = str(text or "")
    chars = list(value)
    if chars and all(_is_latin_letter(ch, QtCore) for ch in chars):
        return "LATIN_WORD"
    if chars and all(ch.isdigit() for ch in chars):
        return "NUMERIC"
    has_digit = any(ch.isdigit() for ch in chars)
    has_punct = any(unicodedata.category(ch).startswith("P") for ch in chars)
    has_symbol = any(unicodedata.category(ch).startswith("S") for ch in chars)
    has_letter = any(ch.isalpha() for ch in chars)
    if has_digit and has_punct and not has_letter and not has_symbol:
        return "PUNCTUATION_NUMERIC"
    if has_symbol and not has_digit and all(ch.isalpha() or unicodedata.category(ch).startswith("S") for ch in chars):
        return "CURRENCY_SYMBOL_SEQUENCE"
    return "MIXED"


def _boundary_type(QtCore, name: str):
    direct = getattr(QtCore.QTextBoundaryFinder, name, None)
    if direct is not None:
        return direct
    enum = getattr(QtCore.QTextBoundaryFinder, "BoundaryType", None)
    return None if enum is None else getattr(enum, name, None)


def boundary_trace(text: str, QtCore) -> dict:
    result = {}
    for name in ("Word", "Grapheme", "Line"):
        boundary_type = _boundary_type(QtCore, name)
        if boundary_type is None:
            result[name.upper()] = {"AVAILABLE": False, "BOUNDARIES": []}
            continue
        finder = QtCore.QTextBoundaryFinder(boundary_type, text)
        finder.setPosition(0)
        rows = [{"POSITION": 0, "REASONS": int(finder.boundaryReasons())}]
        while True:
            pos = int(finder.toNextBoundary())
            if pos < 0:
                break
            rows.append({"POSITION": pos, "REASONS": int(finder.boundaryReasons())})
        result[name.upper()] = {"AVAILABLE": True, "BOUNDARIES": rows}
    result["CHARS"] = [
        {
            "INDEX": index,
            "CHAR": ch,
            "CODEPOINT": f"U+{ord(ch):04X}",
            "UNICODE_CATEGORY": unicodedata.category(ch),
            "UNICODE_NAME": unicodedata.name(ch, "UNKNOWN"),
            "SCRIPT": _script_name(ch, QtCore),
        }
        for index, ch in enumerate(text)
    ]
    return result


def extract_source(pptx: Path, role_ids: dict, QtCore) -> dict:
    with zipfile.ZipFile(pptx) as archive:
        slide_path = "ppt/slides/slide1.xml"
        slide = ET.fromstring(archive.read(slide_path))
        layout_path = _resolve_rel(archive, slide_path, "/slideLayout")
        layout = ET.fromstring(archive.read(layout_path)) if layout_path and layout_path in archive.namelist() else None
        master_path = _resolve_rel(archive, layout_path, "/slideMaster") if layout_path else None
        master = ET.fromstring(archive.read(master_path)) if master_path and master_path in archive.namelist() else None

        nodes = {}
        for profile, roles in role_ids.items():
            nodes[profile] = {}
            for role, shape_id in roles.items():
                shape = _shape_by_id(slide, shape_id)
                if shape is None:
                    raise RuntimeError(f"shape {shape_id} missing")
                paragraphs = shape.findall("./p:txBody/a:p", NS)
                if not paragraphs:
                    raise RuntimeError(f"shape {shape_id} has no paragraph")
                paragraph = paragraphs[0]
                sources = _ppr_sources(shape, paragraph, "slide")
                placeholder = _placeholder_key(shape)
                layout_shape = _matching_placeholder(layout, placeholder) if layout is not None else None
                if layout_shape is not None:
                    layout_paras = layout_shape.findall("./p:txBody/a:p", NS)
                    if layout_paras:
                        sources.extend(_ppr_sources(layout_shape, layout_paras[0], "layout"))
                master_shape = _matching_placeholder(master, placeholder) if master is not None else None
                if master_shape is not None:
                    master_paras = master_shape.findall("./p:txBody/a:p", NS)
                    if master_paras:
                        sources.extend(_ppr_sources(master_shape, master_paras[0], "master"))
                body = shape.find("./p:txBody/a:bodyPr", NS)
                text = _paragraph_text(paragraph)
                attrs = {name: _resolve_attr(name, sources) for name in ATTRS}
                body_raw = {} if body is None else {name: body.get(name) for name in ("wrap", "horzOverflow", "vertOverflow")}
                auto = [] if body is None else [_local(child.tag) for child in list(body)]
                nodes[profile][role] = {
                    "SHAPE_ID": shape_id,
                    "TEXT": text,
                    "TEXT_REPR": repr(text),
                    "PPR_RAW_XML": None if paragraph.find("./a:pPr", NS) is None else ET.tostring(paragraph.find("./a:pPr", NS), encoding="unicode"),
                    "PARAGRAPH_PROPERTIES": attrs,
                    "BODYPR": {
                        "wrap_RAW": body_raw.get("wrap"),
                        "wrap_EFFECTIVE": body_raw.get("wrap") or "square",
                        "horzOverflow_RAW": body_raw.get("horzOverflow"),
                        "horzOverflow_STANDARD_EFFECTIVE": body_raw.get("horzOverflow") or "overflow",
                        "horzOverflow_OFFICE_EFFECTIVE": body_raw.get("horzOverflow") or "overflow",
                        "vertOverflow_RAW": body_raw.get("vertOverflow"),
                        "vertOverflow_EFFECTIVE": body_raw.get("vertOverflow") or "overflow",
                        "spAutoFit": "spAutoFit" in auto,
                    },
                    "TOKEN_CLASS": token_class(text, QtCore),
                    "BOUNDARIES": boundary_trace(text, QtCore),
                    "PLACEHOLDER": None if placeholder is None else {"idx": placeholder[0], "type": placeholder[1]},
                    "INHERITANCE_SOURCES_CHECKED": [name for name, _ in sources],
                }
    return {
        "STANDARD_INTEROP_NOTES": {
            "latinLnBrk": "standard implied default=true; Office default=false when omitted",
            "horzOverflow": "omitted implies overflow",
        },
        "NODES": nodes,
    }


def _layout_tuple(fragment: str, rect, style: dict, font, QtGui, qt_renderer, baseline_index: int = 0):
    metrics = QtGui.QFontMetricsF(font)
    horizontal = str(style.get("align") or "center").lower()
    advance = float(metrics.horizontalAdvance(fragment))
    if horizontal in {"left", "l"}:
        x = float(rect.left())
    elif horizontal in {"right", "r"}:
        x = float(rect.right()) - advance
    else:
        x = float(rect.left()) + (float(rect.width()) - advance) * 0.5
    tight = metrics.tightBoundingRect(fragment)
    first_baseline = float(rect.top()) - float(tight.top())
    line_advance = qt_renderer._pptx_wrapped_line_advance(style, metrics)
    return fragment, x, first_baseline + line_advance * baseline_index


def office_latin_helper(qt_renderer, text: str, rect, style: dict, font, QtCore, QtGui):
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized or "\n" in normalized:
        return None
    if str(style.get("pptx_auto_fit") or "").lower() != "shape" or qt_renderer._should_fit_text(style):
        return None
    if str(style.get("v_align") or style.get("vertical_align") or "center").lower() not in {"top", "t"}:
        return None
    if qt_renderer._pptx_effective_wrap(style) != "square":
        return None
    width = max(0.1, float(rect.width()))
    measure = lambda value: qt_renderer._pptx_source_layout_width(value, style, font, QtGui)
    if float(measure(normalized)) <= width + 0.01:
        return None
    layout_font = qt_renderer._pptx_source_layout_font(style, font, QtGui)
    qtext = qt_renderer._pptx_qtextlayout_fragments(normalized, width, layout_font, QtGui)
    fragments = []
    protected = False
    latin_break = bool(style.get("diagnostic_latin_ln_brk_office_effective", False))
    for fragment in qtext:
        if float(measure(fragment)) <= width + 0.01:
            fragments.append(fragment)
        elif not latin_break and token_class(fragment, QtCore) == "LATIN_WORD":
            fragments.append(fragment)
            protected = True
        else:
            fragments.extend(qt_renderer._pptx_longest_fitting_grapheme_segments(fragment, width, measure, lambda value: qt_renderer._pptx_grapheme_clusters(value, QtCore)))
    if len(fragments) <= 1:
        return [_layout_tuple(fragments[0], rect, style, font, QtGui, qt_renderer)] if fragments and protected else None
    return [_layout_tuple(fragment, rect, style, font, QtGui, qt_renderer, index) for index, fragment in enumerate(fragments)]


def _render_font(style, QtGui, qt_renderer):
    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
    size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    px = size * 96.0 / 72.0 if unit in {"pt", "point", "points"} else size
    font = QtGui.QFont(family)
    font.setPixelSize(max(1, round(px)))
    qt_renderer._set_font_weight(font, style.get("font_weight"), QtGui)
    if style.get("letter_spacing") not in (None, ""):
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))
    return font


def run_office_variant(delegate, args, source_info, out: Path, QtCore, QtGui, qt_renderer):
    original_apply = delegate.apply_variant
    original_probe = delegate.draw_text_probe
    original_helper = qt_renderer._pptx_shape_autofit_wrapped_layout
    from srstudio.graphics2.model import BindingRole
    role_binding = {
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }

    def apply_variant(document, slots, source_semantics, variant):
        original_apply(document, slots, source_semantics, variant)
        for profile, slot in zip(delegate.PROFILE_ORDER, slots):
            for role, binding in role_binding.items():
                node = document.active_page.node(slot.node_by_role[binding.value])
                info = source_info["NODES"][profile][role]
                node.style["diagnostic_latin_ln_brk_office_effective"] = bool(info["PARAGRAPH_PROPERTIES"]["latinLnBrk"]["FINAL_OFFICE_EFFECTIVE"])

    def probe(node, renderer, core, gui, path):
        result = original_probe(node, renderer, core, gui, path)
        font = _render_font(node.style, gui, renderer)
        rect = node.rect.normalized()
        local_rect = core.QRectF(0.0, 0.0, rect.width, rect.height)
        wrapped = renderer._pptx_shape_autofit_wrapped_layout(str(node.text or ""), local_rect, node.style, font, core, gui)
        result["DIAGNOSTIC_TOKEN_CLASS"] = token_class(str(node.text or ""), core)
        result["DIAGNOSTIC_OFFICE_LATIN_LINE_COUNT"] = 0 if wrapped is None else len(wrapped)
        result["DIAGNOSTIC_OFFICE_LATIN_ROUTE"] = "office_latin_wrapped" if wrapped is not None else result.get("LAYOUT_PATH")
        return result

    delegate.apply_variant = apply_variant
    delegate.draw_text_probe = probe
    qt_renderer._pptx_shape_autofit_wrapped_layout = lambda text, rect, style, font, core, gui: office_latin_helper(qt_renderer, text, rect, style, font, core, gui)
    delegate.REQUESTED_SHA = AFTER_SHA
    old_argv = sys.argv[:]
    sys.argv = [str(args.delegate), "--pptx", str(args.pptx), "--source-root", str(args.source_root), "--reference", str(args.reference), "--out", str(out)]
    try:
        code = int(delegate.main())
    finally:
        sys.argv = old_argv
        delegate.apply_variant = original_apply
        delegate.draw_text_probe = original_probe
        qt_renderer._pptx_shape_autofit_wrapped_layout = original_helper
    if code:
        raise RuntimeError(f"office latin variant delegate failed: {code}")


def role_metrics(root: Path) -> tuple[dict, dict]:
    summary = json.loads((root / "text-semantics-summary.json").read_text(encoding="utf-8"))["VARIANTS"]["current"]
    rows = json.loads((root / "text-variant-metrics.json").read_text(encoding="utf-8"))
    current = {(row["PROFILE"], row["ROLE"]): row for row in rows if row.get("VARIANT") == "current"}
    return summary, current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delegate", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.source_root.resolve() / "src"))
    from PySide6 import QtCore, QtGui
    from srstudio.graphics2 import qt_renderer

    spec = importlib.util.spec_from_file_location("latin_delegate", args.delegate.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError("delegate import failed")
    delegate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(delegate)

    source_info = extract_source(args.pptx.resolve(), delegate.ROLE_IDS, QtCore)
    (args.out / "latin-line-break-source.json").write_text(json.dumps(source_info, ensure_ascii=False, indent=2), encoding="utf-8")

    office_dir = args.out / "variant-office-latin"
    run_office_variant(delegate, args, source_info, office_dir, QtCore, QtGui, qt_renderer)
    current_summary, current_rows = role_metrics(args.current.resolve())
    office_summary, office_rows = role_metrics(office_dir)

    synthetic = []
    for latin_break, text in ((False, "KG"), (True, "KG"), (False, ",86"), (False, "R$")):
        font = QtGui.QFont("Arial")
        font.setPixelSize(18)
        style = {"align": "center", "v_align": "top", "nowrap": False, "pptx_wrap": "square", "pptx_auto_fit": "shape", "fit_inside_box": False, "semantic_fit_policy": "preserve_source_typography", "font_size": 13.5, "font_size_unit": "pt", "diagnostic_latin_ln_brk_office_effective": latin_break}
        rect = QtCore.QRectF(0.0, 0.0, max(4.0, QtGui.QFontMetricsF(font).horizontalAdvance(text) * 0.58), 20.0)
        current = qt_renderer._pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui)
        office = office_latin_helper(qt_renderer, text, rect, style, font, QtCore, QtGui)
        synthetic.append({"latinLnBrk_OFFICE_EFFECTIVE": latin_break, "TEXT": text, "TOKEN_CLASS": token_class(text, QtCore), "CURRENT_LINE_COUNT": 0 if current is None else len(current), "OFFICE_LATIN_LINE_COUNT": 0 if office is None else len(office), "RECT_WIDTH": float(rect.width())})

    role_compare = {}
    for role in delegate.ROLE_ORDER:
        role_compare[role] = {
            "CURRENT_MAE": float(current_summary["ROLE_MAE"][role]),
            "OFFICE_LATIN_MAE": float(office_summary["ROLE_MAE"][role]),
            "MAE_DELTA": float(office_summary["ROLE_MAE"][role]) - float(current_summary["ROLE_MAE"][role]),
            "CURRENT_CHANGED_RATIO": float(current_summary["ROLE_CHANGED_RATIO"][role]),
            "OFFICE_LATIN_CHANGED_RATIO": float(office_summary["ROLE_CHANGED_RATIO"][role]),
            "CHANGED_RATIO_DELTA": float(office_summary["ROLE_CHANGED_RATIO"][role]) - float(current_summary["ROLE_CHANGED_RATIO"][role]),
        }

    unit_ok = all(source_info["NODES"][p]["unit"]["TOKEN_CLASS"] == "LATIN_WORD" and source_info["NODES"][p]["unit"]["PARAGRAPH_PROPERTIES"]["latinLnBrk"]["FINAL_OFFICE_EFFECTIVE"] is False and int(office_rows[(p, "unit")].get("LINE_COUNT") or 0) == 1 for p in delegate.PROFILE_ORDER)
    currency_ok = all(source_info["NODES"][p]["currency"]["TOKEN_CLASS"] != "LATIN_WORD" and int(office_rows[(p, "currency")].get("LINE_COUNT") or 0) > 1 for p in delegate.PROFILE_ORDER)
    decimal_ok = all(source_info["NODES"][p]["decimal"]["TOKEN_CLASS"] != "LATIN_WORD" and int(office_rows[(p, "decimal")].get("LINE_COUNT") or 0) > 1 for p in delegate.PROFILE_ORDER)
    eps = 1e-9
    controls_ok = all(role_compare[r]["OFFICE_LATIN_MAE"] <= role_compare[r]["CURRENT_MAE"] + eps and role_compare[r]["OFFICE_LATIN_CHANGED_RATIO"] <= role_compare[r]["CURRENT_CHANGED_RATIO"] + eps for r in ("currency", "decimal", "integer", "name"))
    confirmed = unit_ok and currency_ok and decimal_ok and controls_ok

    result = {
        "AFTER_SHA": AFTER_SHA,
        "PPTX_SHA256": PPTX_SHA,
        "PRODUCTION_FILES_CHANGED": 0,
        "KG_TOKEN_CLASS": token_class("KG", QtCore),
        "DECIMAL_TOKEN_CLASS": token_class(",86", QtCore),
        "CURRENCY_TOKEN_CLASS": token_class("R$", QtCore),
        "KG_BREAK_OPPORTUNITIES": boundary_trace("KG", QtCore),
        "DECIMAL_BREAK_OPPORTUNITIES": boundary_trace(",86", QtCore),
        "CURRENCY_BREAK_OPPORTUNITIES": boundary_trace("R$", QtCore),
        "VARIANT_CURRENT": current_summary,
        "VARIANT_OFFICE_LATIN_RULE": office_summary,
        "ROLE_COMPARE": role_compare,
        "SYNTHETIC_CASES": synthetic,
        "UNIT_SINGLE_LINE_4_OF_4": unit_ok,
        "CURRENCY_WRAPPED_4_OF_4": currency_ok,
        "DECIMAL_WRAPPED_4_OF_4": decimal_ok,
        "CONTROLS_NO_REGRESSION": controls_ok,
        "ROOT_CAUSE_CONFIRMED": confirmed,
        "READY_TO_MODIFY_PR_111": confirmed,
    }
    (args.out / "latin-line-break-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
