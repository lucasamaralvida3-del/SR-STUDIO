from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

AFTER_SHA = "2e706558132e8893377c0dd6772d55c6c9d3a739"
PPTX_SHA = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path.resolve())
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def internal_positions(boundary_payload: dict, key: str, length: int) -> set[int]:
    rows = boundary_payload.get(key, {}).get("BOUNDARIES", [])
    return {int(row["POSITION"]) for row in rows if 0 < int(row["POSITION"]) < length}


def latin_spans(text: str, latin, QtCore) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = None
    for index, ch in enumerate(text):
        is_latin = latin._is_latin_letter(ch, QtCore)
        if is_latin and start is None:
            start = index
        if not is_latin and start is not None:
            spans.append((start, index))
            start = None
    if start is not None:
        spans.append((start, len(text)))
    return spans


def break_plan(text: str, latin_ln_brk: bool, horz_overflow: str, latin, QtCore) -> dict:
    trace = latin.boundary_trace(text, QtCore)
    n = len(text)
    grapheme = internal_positions(trace, "GRAPHEME", n)
    word = internal_positions(trace, "WORD", n)
    line = internal_positions(trace, "LINE", n)
    spans = latin_spans(text, latin, QtCore)
    decisions = []
    allowed: list[int] = []
    for pos in sorted(grapheme | word | line):
        inside_latin = next(((a, b) for a, b in spans if a < pos < b), None)
        sources = []
        if pos in grapheme:
            sources.append("grapheme")
        if pos in word:
            sources.append("word")
        if pos in line:
            sources.append("qt-line")
        if not latin_ln_brk and inside_latin is not None:
            status = "FORBIDDEN"
            reason = "latinLnBrk=false inside LATIN_WORD"
        else:
            status = "ALLOWED"
            if pos in line:
                reason = "Qt/Unicode line boundary"
            elif pos in word:
                reason = "Qt/Unicode word boundary"
            else:
                reason = "Unicode grapheme fallback outside protected LATIN_WORD"
            allowed.append(pos)
        decisions.append({
            "POSITION": pos,
            "STATUS": status,
            "REASON": reason,
            "SOURCES": sources,
            "LATIN_SPAN": None if inside_latin is None else list(inside_latin),
        })
    return {
        "TEXT": text,
        "TOKEN_CLASS": latin.token_class(text, QtCore),
        "LATIN_SPANS": [list(span) for span in spans],
        "GRAPHEME_BOUNDARIES": sorted(grapheme),
        "WORD_BOUNDARIES": sorted(word),
        "QT_LINE_BOUNDARIES": sorted(line),
        "CANDIDATE_BREAK_POSITIONS": sorted(grapheme | word | line),
        "OFFICE_FILTERED_BREAK_POSITIONS": allowed,
        "DECISIONS": decisions,
        "latinLnBrk_OFFICE_EFFECTIVE": bool(latin_ln_brk),
        "horzOverflow_OFFICE_EFFECTIVE": horz_overflow,
        "BOUNDARY_TRACE": trace,
    }


def build_lines(text: str, width: float, measure, plan: dict) -> list[str]:
    if not text:
        return [""]
    allowed = sorted(set(int(p) for p in plan["OFFICE_FILTERED_BREAK_POSITIONS"] if 0 < int(p) < len(text)))
    endpoints = allowed + [len(text)]
    lines: list[str] = []
    start = 0
    while start < len(text):
        fitting = [p for p in endpoints if p > start and float(measure(text[start:p])) <= width + 0.01]
        if fitting:
            end = max(fitting)
            lines.append(text[start:end])
            start = end
            continue
        next_break = next((p for p in endpoints if p > start), len(text))
        # No legal unit fits. Office-effective horzOverflow=overflow keeps the
        # next indivisible unit intact instead of inventing an illegal split.
        lines.append(text[start:next_break])
        start = next_break
    return lines


def planner_helper(qt_renderer, latin, text: str, rect, style: dict, font, QtCore, QtGui):
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
    latin_break = bool(style.get("diagnostic_latin_ln_brk_office_effective", False))
    horz = str(style.get("diagnostic_horz_overflow_office_effective") or "overflow")
    plan = break_plan(normalized, latin_break, horz, latin, QtCore)
    fragments = build_lines(normalized, width, measure, plan)
    if not fragments:
        return None
    return [latin._layout_tuple(fragment, rect, style, font, QtGui, qt_renderer, index) for index, fragment in enumerate(fragments)]


def enrich_probe(delegate, node, renderer, core, gui, path: Path) -> dict:
    base = delegate._planner_original_probe(node, renderer, core, gui, path)
    style = node.style
    size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    pixel_size = size * 96.0 / 72.0 if unit in {"pt", "point", "points"} else size
    rect = node.rect.normalized()
    base.update({
        "DIAG_NODE_TRANSFORM": repr(getattr(node, "transform", None)),
        "DIAG_RECT": [float(rect.x), float(rect.y), float(rect.width), float(rect.height)],
        "DIAG_TEXT": str(node.text or ""),
        "DIAG_FONT": str(style.get("font_family") or style.get("source_font_family") or "Segoe UI"),
        "DIAG_PIXEL_SIZE": pixel_size,
        "DIAG_LETTER_SPACING": float(style.get("letter_spacing") or 0.0),
        "DIAG_OPACITY": float(getattr(node, "opacity", style.get("opacity", 1.0)) or 0.0),
        "DIAG_Z": repr(getattr(node, "z", getattr(node, "z_index", None))),
        "DIAG_PAINTER_STATE": {"TextAntialiasing": True, "probe_scale": float(getattr(delegate, "RASTER_SCALE", 2.0))},
        "DIAG_PROBE_SHA256": sha256(path),
    })
    return base


def run_delegate(delegate, args, out: Path, source_info: dict, latin, QtCore, QtGui, qt_renderer, planner: bool) -> None:
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
    delegate._planner_original_probe = original_probe

    def apply_variant(document, slots, source_semantics, variant):
        original_apply(document, slots, source_semantics, variant)
        if not planner:
            return
        for profile, slot in zip(delegate.PROFILE_ORDER, slots):
            for role, binding in role_binding.items():
                node = document.active_page.node(slot.node_by_role[binding.value])
                info = source_info["NODES"][profile][role]
                node.style["diagnostic_latin_ln_brk_office_effective"] = bool(
                    info["PARAGRAPH_PROPERTIES"]["latinLnBrk"]["FINAL_OFFICE_EFFECTIVE"]
                )
                node.style["diagnostic_horz_overflow_office_effective"] = str(
                    info["BODYPR"]["horzOverflow_OFFICE_EFFECTIVE"] or "overflow"
                )

    def probe(node, renderer, core, gui, path):
        return enrich_probe(delegate, node, renderer, core, gui, path)

    delegate.apply_variant = apply_variant
    delegate.draw_text_probe = probe
    if planner:
        qt_renderer._pptx_shape_autofit_wrapped_layout = (
            lambda text, rect, style, font, core, gui: planner_helper(qt_renderer, latin, text, rect, style, font, core, gui)
        )
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
        delattr(delegate, "_planner_original_probe")
    if code:
        raise RuntimeError(f"delegate failed: {code}")


def current_rows(root: Path) -> dict[tuple[str, str], dict]:
    rows = json.loads((root / "text-variant-metrics.json").read_text(encoding="utf-8"))
    return {(row["PROFILE"], row["ROLE"]): row for row in rows if row.get("VARIANT") == "current"}


def summary(root: Path) -> dict:
    return json.loads((root / "text-semantics-summary.json").read_text(encoding="utf-8"))["VARIANTS"]["current"]


def crop_sha(root: Path, profile: str, role: str) -> str:
    return sha256(root / "crops" / f"current-{profile}-{role}.png")


def probe_sha(root: Path, profile: str, role: str) -> str:
    return sha256(root / "probes" / f"current-{profile}-{role}.png")


def role_compare(current_root: Path, planner_root: Path, roles) -> dict:
    cur = summary(current_root)
    planned = summary(planner_root)
    result = {}
    for role in roles:
        result[role] = {
            "CURRENT_MAE": float(cur["ROLE_MAE"][role]),
            "PLANNER_MAE": float(planned["ROLE_MAE"][role]),
            "MAE_DELTA": float(planned["ROLE_MAE"][role]) - float(cur["ROLE_MAE"][role]),
            "CURRENT_CHANGED_RATIO": float(cur["ROLE_CHANGED_RATIO"][role]),
            "PLANNER_CHANGED_RATIO": float(planned["ROLE_CHANGED_RATIO"][role]),
            "CHANGED_RATIO_DELTA": float(planned["ROLE_CHANGED_RATIO"][role]) - float(cur["ROLE_CHANGED_RATIO"][role]),
        }
    return result


def synthetic_case(text: str, latin_break: bool, width_factor: float, latin, QtCore, QtGui, qt_renderer) -> dict:
    font = QtGui.QFont("Arial")
    font.setPixelSize(18)
    style = {
        "align": "center",
        "v_align": "top",
        "nowrap": False,
        "pptx_wrap": "square",
        "pptx_auto_fit": "shape",
        "fit_inside_box": False,
        "semantic_fit_policy": "preserve_source_typography",
        "font_size": 13.5,
        "font_size_unit": "pt",
        "diagnostic_latin_ln_brk_office_effective": latin_break,
        "diagnostic_horz_overflow_office_effective": "overflow",
    }
    measure = lambda value: qt_renderer._pptx_source_layout_width(value, style, font, QtGui)
    width = max(3.0, float(measure(text)) * width_factor)
    plan = break_plan(text, latin_break, "overflow", latin, QtCore)
    lines = build_lines(text, width, measure, plan)
    return {
        "TEXT": text,
        "latinLnBrk_OFFICE_EFFECTIVE": latin_break,
        "RECT_WIDTH": width,
        "FULL_ADVANCE": float(measure(text)),
        "LINES": lines,
        "LINE_COUNT": len(lines),
        "OVERFLOWING_LINES": [line for line in lines if float(measure(line)) > width + 0.01],
        "PLAN": plan,
    }


def integer_root_cause(current1: Path, current2: Path, planner1: Path, planner2: Path, profiles, rows_current, rows_planner) -> dict:
    evidence = []
    current_repeat_equal = True
    planner_repeat_equal = True
    planner_vs_current_crop_equal = True
    planner_vs_current_probe_equal = True
    input_equal = True
    for profile in profiles:
        c1_crop = crop_sha(current1, profile, "integer")
        c2_crop = crop_sha(current2, profile, "integer")
        p1_crop = crop_sha(planner1, profile, "integer")
        p2_crop = crop_sha(planner2, profile, "integer")
        c1_probe = probe_sha(current1, profile, "integer")
        c2_probe = probe_sha(current2, profile, "integer")
        p1_probe = probe_sha(planner1, profile, "integer")
        p2_probe = probe_sha(planner2, profile, "integer")
        c = rows_current[(profile, "integer")]
        p = rows_planner[(profile, "integer")]
        fields = ["TEXT_REPR", "SOURCE_WRAP_RAW", "SOURCE_WRAP_EFFECTIVE", "RUNTIME_NOWRAP", "DIAG_RECT", "DIAG_TEXT", "DIAG_FONT", "DIAG_PIXEL_SIZE", "DIAG_LETTER_SPACING", "LAYOUT_PATH", "DIAG_NODE_TRANSFORM", "DIAG_OPACITY", "DIAG_Z", "DIAG_PAINTER_STATE", "CROP_BOX"]
        same_inputs = all(c.get(field) == p.get(field) for field in fields)
        input_equal &= same_inputs
        current_repeat_equal &= c1_crop == c2_crop and c1_probe == c2_probe
        planner_repeat_equal &= p1_crop == p2_crop and p1_probe == p2_probe
        planner_vs_current_crop_equal &= c1_crop == p1_crop
        planner_vs_current_probe_equal &= c1_probe == p1_probe
        evidence.append({
            "PROFILE": profile,
            "INPUTS_IDENTICAL": same_inputs,
            "CURRENT_CROP_SHA": c1_crop,
            "PLANNER_CROP_SHA": p1_crop,
            "CURRENT_PROBE_SHA": c1_probe,
            "PLANNER_PROBE_SHA": p1_probe,
            "CURRENT_REPEAT_CROP_EQUAL": c1_crop == c2_crop,
            "PLANNER_REPEAT_CROP_EQUAL": p1_crop == p2_crop,
            "CURRENT_REPEAT_PROBE_EQUAL": c1_probe == c2_probe,
            "PLANNER_REPEAT_PROBE_EQUAL": p1_probe == p2_probe,
            "INPUTS": {field: {"CURRENT": c.get(field), "PLANNER": p.get(field)} for field in fields},
        })
    if not current_repeat_equal or not planner_repeat_equal:
        classification = "NONDETERMINISM"
    elif input_equal and planner_vs_current_probe_equal and not planner_vs_current_crop_equal:
        classification = "COMPOSITING EFFECT"
    elif input_equal and planner_vs_current_probe_equal and planner_vs_current_crop_equal:
        classification = "CROP/METRIC HARNESS ARTIFACT"
    elif input_equal and not planner_vs_current_probe_equal:
        classification = "REAL RENDER REGRESSION"
    else:
        classification = "INPUT/ROUTE DIFFERENCE"
    return {
        "CLASSIFICATION": classification,
        "CURRENT_REPEAT_EQUAL": current_repeat_equal,
        "PLANNER_REPEAT_EQUAL": planner_repeat_equal,
        "INPUTS_IDENTICAL": input_equal,
        "PLANNER_VS_CURRENT_CROP_EQUAL": planner_vs_current_crop_equal,
        "PLANNER_VS_CURRENT_ISOLATED_PROBE_EQUAL": planner_vs_current_probe_equal,
        "PER_PROFILE": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delegate", required=True, type=Path)
    parser.add_argument("--latin-module", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if sha256(args.pptx) != PPTX_SHA:
        raise RuntimeError("exact PPTX SHA mismatch")
    sys.path.insert(0, str(args.source_root.resolve() / "src"))
    from PySide6 import QtCore, QtGui
    from srstudio.graphics2 import qt_renderer

    delegate = load_module(args.delegate, "planner_delegate")
    latin = load_module(args.latin_module, "planner_latin")
    source_info = latin.extract_source(args.pptx.resolve(), delegate.ROLE_IDS, QtCore)

    plans = {}
    for text, key in (("KG", "KG"), (",86", "DECIMAL"), ("R$", "CURRENCY")):
        plans[key] = break_plan(text, False, "overflow", latin, QtCore)
    (args.out / "line-break-plans.json").write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")

    synthetic = {
        "KG_FALSE": synthetic_case("KG", False, 0.58, latin, QtCore, QtGui, qt_renderer),
        "KG_TRUE": synthetic_case("KG", True, 0.58, latin, QtCore, QtGui, qt_renderer),
        "DECIMAL_FALSE": synthetic_case(",86", False, 0.58, latin, QtCore, QtGui, qt_renderer),
        "CURRENCY_FALSE": synthetic_case("R$", False, 0.58, latin, QtCore, QtGui, qt_renderer),
        "AB_CD_FALSE": synthetic_case("AB CD", False, 0.62, latin, QtCore, QtGui, qt_renderer),
    }

    current1 = args.out / "current-run1"
    current2 = args.out / "current-run2"
    planner1 = args.out / "planner-run1"
    planner2 = args.out / "planner-run2"
    run_delegate(delegate, args, current1, source_info, latin, QtCore, QtGui, qt_renderer, False)
    run_delegate(delegate, args, current2, source_info, latin, QtCore, QtGui, qt_renderer, False)
    run_delegate(delegate, args, planner1, source_info, latin, QtCore, QtGui, qt_renderer, True)
    run_delegate(delegate, args, planner2, source_info, latin, QtCore, QtGui, qt_renderer, True)

    current_page_equal = sha256(current1 / "_page-current.png") == sha256(current2 / "_page-current.png")
    planner_page_equal = sha256(planner1 / "_page-current.png") == sha256(planner2 / "_page-current.png")
    rows_current = current_rows(current1)
    rows_planner = current_rows(planner1)
    integer = integer_root_cause(current1, current2, planner1, planner2, delegate.PROFILE_ORDER, rows_current, rows_planner)
    name_deterministic = all(
        crop_sha(current1, p, "name") == crop_sha(current2, p, "name")
        and crop_sha(planner1, p, "name") == crop_sha(planner2, p, "name")
        and probe_sha(current1, p, "name") == probe_sha(current2, p, "name")
        and probe_sha(planner1, p, "name") == probe_sha(planner2, p, "name")
        for p in delegate.PROFILE_ORDER
    )

    real_lines = {}
    for role in ("currency", "decimal", "unit", "integer", "name"):
        real_lines[role] = {p: int(rows_planner[(p, role)].get("LINE_COUNT") or 0) for p in delegate.PROFILE_ORDER}
    currency_ok = all(value == 2 for value in real_lines["currency"].values())
    decimal_ok = all(value == 2 for value in real_lines["decimal"].values())
    unit_ok = all(value == 1 for value in real_lines["unit"].values())
    synthetic_ok = (
        synthetic["KG_FALSE"]["LINE_COUNT"] == 1
        and bool(synthetic["KG_FALSE"]["OVERFLOWING_LINES"])
        and synthetic["KG_TRUE"]["LINE_COUNT"] > 1
        and synthetic["DECIMAL_FALSE"]["LINE_COUNT"] > 1
        and synthetic["CURRENCY_FALSE"]["LINE_COUNT"] > 1
        and synthetic["AB_CD_FALSE"]["PLAN"]["DECISIONS"][0]["STATUS"] == "FORBIDDEN"
    )
    controls_explained = integer["CLASSIFICATION"] != "REAL RENDER REGRESSION" and integer["CLASSIFICATION"] != "NONDETERMINISM"
    generic_possible = synthetic_ok and currency_ok and decimal_ok and unit_ok and current_page_equal and planner_page_equal and controls_explained and name_deterministic

    result = {
        "AFTER_SHA": AFTER_SHA,
        "PPTX_SHA256": PPTX_SHA,
        "LINE_BREAK_PLANNER_MODEL": "pre-layout custom line builder over Unicode/QTextBoundaryFinder candidates; latinLnBrk=false filters internal LATIN_WORD boundaries; horzOverflow=overflow preserves oversized indivisible units",
        "KG_OFFICE_FILTERED_BREAKS": plans["KG"]["OFFICE_FILTERED_BREAK_POSITIONS"],
        "DECIMAL_OFFICE_FILTERED_BREAKS": plans["DECIMAL"]["OFFICE_FILTERED_BREAK_POSITIONS"],
        "CURRENCY_OFFICE_FILTERED_BREAKS": plans["CURRENCY"]["OFFICE_FILTERED_BREAK_POSITIONS"],
        "SYNTHETIC": synthetic,
        "REAL_LINE_COUNTS": real_lines,
        "ROLE_METRICS": role_compare(current1, planner1, delegate.ROLE_ORDER),
        "CURRENT_RUN1_FULL_PAGE_SHA": sha256(current1 / "_page-current.png"),
        "CURRENT_RUN2_FULL_PAGE_SHA": sha256(current2 / "_page-current.png"),
        "PLANNER_RUN1_FULL_PAGE_SHA": sha256(planner1 / "_page-current.png"),
        "PLANNER_RUN2_FULL_PAGE_SHA": sha256(planner2 / "_page-current.png"),
        "CURRENT_RUN1_EQ_RUN2": current_page_equal,
        "PLANNER_RUN1_EQ_RUN2": planner_page_equal,
        "INTEGER_DELTA_ROOT_CAUSE": integer,
        "INTEGER_DETERMINISTIC": integer["CURRENT_REPEAT_EQUAL"] and integer["PLANNER_REPEAT_EQUAL"],
        "NAME_DETERMINISTIC": name_deterministic,
        "REAL_CURRENCY_OK": currency_ok,
        "REAL_DECIMAL_OK": decimal_ok,
        "REAL_UNIT_OK": unit_ok,
        "SYNTHETIC_OK": synthetic_ok,
        "GENERIC_IMPLEMENTATION_POSSIBLE": generic_possible,
        "PRODUCTION_FILES_CHANGED": 0,
        "READY_TO_MODIFY_PR_111": generic_possible,
    }
    (args.out / "office-line-break-planner-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
