from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

AFTER_SHA = "2e706558132e8893377c0dd6772d55c6c9d3a739"
PPTX_SHA = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
VARIANT_ORDER = ("A", "B", "C", "D")


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


def forced_segments(label: str, text: str) -> list[str]:
    value = str(text or "")
    if len(value) != 3:
        raise RuntimeError(f"decimal diagnostic expects 3 chars, got {value!r}")
    if label == "A":
        return [value]
    if label == "B":
        return [value[:1], value[1:]]
    if label == "C":
        return [value[:2], value[2:]]
    if label == "D":
        return [value[:1], value[1:2], value[2:]]
    raise RuntimeError(label)


def line_break_class(ch: str, regex_module) -> str:
    classes = (
        "AI", "AL", "B2", "BA", "BB", "BK", "CB", "CJ", "CL", "CM", "CP", "CR",
        "EB", "EM", "EX", "GL", "H2", "H3", "HL", "HY", "ID", "IN", "IS", "JL",
        "JT", "JV", "LF", "NL", "NS", "NU", "OP", "PO", "PR", "QU", "RI", "SA",
        "SG", "SP", "SY", "WJ", "XX", "ZW", "ZWJ",
    )
    for value in classes:
        if regex_module.fullmatch(rf"\p{{Line_Break={value}}}", ch):
            return value
    return "UNKNOWN"


def render_font(style: dict, QtGui, qt_renderer):
    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
    size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    px = size * 96.0 / 72.0 if unit in {"pt", "point", "points"} else size
    font = QtGui.QFont(family)
    font.setPixelSize(max(1, round(px)))
    qt_renderer._set_font_weight(font, style.get("font_weight"), QtGui)
    font.setItalic(bool(style.get("italic")))
    if style.get("letter_spacing") not in (None, ""):
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))
    return font


def decision_trace(text: str, rect, style: dict, font, planner, latin, qt_renderer, QtCore, QtGui, production_helper) -> dict:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    width = max(0.1, float(rect.width()))
    source_font = qt_renderer._pptx_source_layout_font(style, font, QtGui)
    source_metrics = QtGui.QFontMetricsF(source_font)

    def advance(value: str) -> float:
        return float(source_metrics.horizontalAdvance(value))

    def ink(value: str) -> float:
        return float(source_metrics.tightBoundingRect(value).width())

    def source_width(value: str) -> float:
        return float(qt_renderer._pptx_source_layout_width(value, style, font, QtGui))

    whole_advance = advance(normalized)
    whole_ink = ink(normalized)
    whole_source = source_width(normalized)
    latin_break = bool(style.get("diagnostic_latin_ln_brk_office_effective", False))
    horz = str(style.get("diagnostic_horz_overflow_office_effective") or "overflow")
    plan = planner.break_plan(normalized, latin_break, horz, latin, QtCore)
    allowed = sorted({int(pos) for pos in plan["OFFICE_FILTERED_BREAK_POSITIONS"] if 0 < int(pos) < len(normalized)})
    endpoints = allowed + [len(normalized)]
    prefix_rows = []
    segments = []
    start = 0
    chosen_positions = []
    while start < len(normalized):
        evaluated = []
        for end in endpoints:
            if end <= start:
                continue
            value = normalized[start:end]
            row = {
                "START": start,
                "END": end,
                "PREFIX": value,
                "PREFIX_ADVANCE": advance(value),
                "PREFIX_INK_WIDTH": ink(value),
                "PREFIX_SOURCE_WIDTH": source_width(value),
            }
            row["PREFIX_ACCEPTED"] = bool(row["PREFIX_SOURCE_WIDTH"] <= width + 0.01)
            evaluated.append(row)
        fitting = [row for row in evaluated if row["PREFIX_ACCEPTED"]]
        if fitting:
            selected = max(fitting, key=lambda row: int(row["END"]))
            end = int(selected["END"])
        else:
            end = next((pos for pos in endpoints if pos > start), len(normalized))
        prefix_rows.append({"START": start, "PREFIXES_EVALUATED": evaluated, "BREAK_POSITION_CHOSEN": end})
        segments.append(normalized[start:end])
        chosen_positions.append(end)
        start = end

    emergency_layout = production_helper(normalized, rect, style, font, QtCore, QtGui)
    emergency_segments = [] if emergency_layout is None else [str(row[0]) for row in emergency_layout]
    qtext_line_positions = [
        int(row["POSITION"])
        for row in plan["BOUNDARY_TRACE"].get("LINE", {}).get("BOUNDARIES", [])
        if 0 < int(row["POSITION"]) < len(normalized)
    ]
    return {
        "TEXT": normalized,
        "WHOLE_TOKEN_ADVANCE": whole_advance,
        "WHOLE_TOKEN_INK_WIDTH": whole_ink,
        "WHOLE_TOKEN_SOURCE_WIDTH": whole_source,
        "AVAILABLE_WIDTH": width,
        "WHOLE_TOKEN_FITS_BY_ADVANCE": bool(whole_advance <= width + 0.01),
        "WHOLE_TOKEN_FITS_BY_INK": bool(whole_ink <= width + 0.01),
        "EARLY_RETURN_SINGLE_LINE": bool(whole_source <= width + 0.01),
        "CANDIDATE_BREAK_POSITIONS": plan["CANDIDATE_BREAK_POSITIONS"],
        "OFFICE_FILTERED_BREAK_POSITIONS": plan["OFFICE_FILTERED_BREAK_POSITIONS"],
        "QTEXTBOUNDARYFINDER_LINE_INTERNAL": qtext_line_positions,
        "PREFIXES_EVALUATED": prefix_rows,
        "BREAK_POSITION_CHOSEN": chosen_positions,
        "REMAINDER": "" if not chosen_positions else normalized[chosen_positions[-1]:],
        "FINAL_SEGMENTS": segments,
        "CURRENT_EMERGENCY_SEGMENTS": emergency_segments,
        "latinLnBrk_OFFICE_EFFECTIVE": latin_break,
        "horzOverflow_OFFICE_EFFECTIVE": horz,
        "wrap_EFFECTIVE": str(style.get("pptx_wrap") or ""),
        "spAutoFit": str(style.get("pptx_auto_fit") or "").lower() == "shape",
        "PLAN": plan,
    }


def current_row(root: Path, profile: str, role: str = "decimal") -> dict:
    rows = json.loads((root / "text-variant-metrics.json").read_text(encoding="utf-8"))
    for row in rows:
        if row.get("VARIANT") == "current" and row.get("PROFILE") == profile and row.get("ROLE") == role:
            return row
    raise RuntimeError(f"row missing: {profile}/{role}")


def run_forced(delegate, planner, latin, args, source_info, label: str, out: Path, QtCore, QtGui, qt_renderer, traces: dict, layout_capture: dict, production_helper) -> None:
    from srstudio.graphics2.model import BindingRole

    original_apply = delegate.apply_variant
    original_planner_helper = planner.planner_helper

    def apply_variant(document, slots, source_semantics, variant):
        original_apply(document, slots, source_semantics, variant)
        for profile, slot in zip(delegate.PROFILE_ORDER, slots):
            node = document.active_page.node(slot.node_by_role[BindingRole.PRICE_CENTS.value])
            node.style["diagnostic_decimal_profile"] = profile
            node.style["diagnostic_forced_segments"] = forced_segments(label, str(node.text or ""))

    def helper(renderer, latin_module, text, rect, style, font, core, gui):
        profile = style.get("diagnostic_decimal_profile")
        forced = style.get("diagnostic_forced_segments")
        if profile and forced:
            key = str(profile)
            if key not in traces:
                traces[key] = decision_trace(str(text or ""), rect, style, font, planner, latin_module, renderer, core, gui, production_helper)
            layout = [latin_module._layout_tuple(fragment, rect, style, font, gui, renderer, index) for index, fragment in enumerate(list(forced))]
            layout_capture.setdefault(label, {})[key] = {
                "SEGMENTS": [str(row[0]) for row in layout],
                "BASELINES": [float(row[2]) for row in layout],
                "X": [float(row[1]) for row in layout],
            }
            return layout
        return original_planner_helper(renderer, latin_module, text, rect, style, font, core, gui)

    delegate.apply_variant = apply_variant
    planner.planner_helper = helper
    try:
        planner.run_delegate(delegate, args, out, source_info, latin, QtCore, QtGui, qt_renderer, True)
    finally:
        delegate.apply_variant = original_apply
        planner.planner_helper = original_planner_helper


def copy_crop_and_metrics(args, label: str, run1: Path, run2: Path, profile: str, layout_capture: dict) -> dict:
    crop1 = run1 / "crops" / f"current-{profile}-decimal.png"
    crop2 = run2 / "crops" / f"current-{profile}-decimal.png"
    flat = args.out / "decimal-crops"
    flat.mkdir(parents=True, exist_ok=True)
    copied = flat / f"{profile}-{label}.png"
    shutil.copy2(crop1, copied)
    row = current_row(run1, profile)
    row2 = current_row(run2, profile)
    return {
        "VARIANT": label,
        "SEGMENTS": forced_segments(label, str(row.get("TEXT") or row.get("DIAG_TEXT") or "")),
        "MAE": float(row.get("MAE") or 0.0),
        "CHANGED_RATIO": float(row.get("CHANGED_RATIO") or 0.0),
        "BBOX": row.get("RENDERED_BBOX"),
        "BAND_COUNT": int(row.get("LINE_COUNT") or 0),
        "BAND_Y_RANGES": row.get("LINE_BANDS") or [],
        "BASELINES": layout_capture.get(label, {}).get(profile, {}).get("BASELINES", []),
        "CROP_SHA": sha256(crop1),
        "REPEAT_CROP_SHA": sha256(crop2),
        "CROP_DETERMINISTIC": sha256(crop1) == sha256(crop2),
        "FULL_PAGE_SHA": sha256(run1 / "_page-current.png"),
        "REPEAT_FULL_PAGE_SHA": sha256(run2 / "_page-current.png"),
        "FULL_PAGE_DETERMINISTIC": sha256(run1 / "_page-current.png") == sha256(run2 / "_page-current.png"),
        "CROP_FILE": str(copied.relative_to(args.out)).replace("\\", "/"),
        "CROP_BOX": row.get("CROP_BOX"),
        "REPEAT_MAE": float(row2.get("MAE") or 0.0),
        "REPEAT_CHANGED_RATIO": float(row2.get("CHANGED_RATIO") or 0.0),
    }


def make_side_by_side(args, profile: str, best: dict, baseline_root: Path) -> str:
    from PIL import Image, ImageDraw

    box = tuple(int(v) for v in best["CROP_BOX"])
    reference = Image.open(args.reference).convert("RGB").crop(box)
    best_img = Image.open(args.out / best["CROP_FILE"]).convert("RGB")
    emergency = Image.open(baseline_root / "crops" / f"current-{profile}-decimal.png").convert("RGB")
    width = reference.width + best_img.width + emergency.width
    header = 24
    canvas = Image.new("RGB", (width, max(reference.height, best_img.height, emergency.height) + header), "white")
    draw = ImageDraw.Draw(canvas)
    x = 0
    for label, image in (("REFERENCE", reference), (f"BEST {best['VARIANT']}", best_img), ("CURRENT EMERGENCY", emergency)):
        draw.text((x + 3, 4), label, fill="black")
        canvas.paste(image, (x, header))
        x += image.width
    out_dir = args.out / "side-by-side"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{profile}-best.png"
    canvas.save(output)
    return str(output.relative_to(args.out)).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner-module", required=True, type=Path)
    parser.add_argument("--delegate", required=True, type=Path)
    parser.add_argument("--latin-module", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--baseline-planner", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if sha256(args.pptx) != PPTX_SHA:
        raise RuntimeError("exact PPTX SHA mismatch")
    sys.path.insert(0, str(args.source_root.resolve() / "src"))

    import regex
    from PySide6 import QtCore, QtGui
    from srstudio.graphics2 import qt_renderer
    from srstudio.graphics2.fonts import ensure_qgui_application

    app = ensure_qgui_application()
    app.processEvents()
    delegate = load_module(args.delegate, "decimal_final_delegate")
    planner = load_module(args.planner_module, "decimal_final_planner")
    latin = load_module(args.latin_module, "decimal_final_latin")
    source_info = latin.extract_source(args.pptx.resolve(), delegate.ROLE_IDS, QtCore)
    production_helper = qt_renderer._pptx_shape_autofit_wrapped_layout

    traces: dict[str, dict] = {}
    layout_capture: dict[str, dict] = {}
    roots: dict[str, tuple[Path, Path]] = {}
    for label in VARIANT_ORDER:
        run1 = args.out / "variants" / f"{label}-run1"
        run2 = args.out / "variants" / f"{label}-run2"
        run_forced(delegate, planner, latin, args, source_info, label, run1, QtCore, QtGui, qt_renderer, traces, layout_capture, production_helper)
        run_forced(delegate, planner, latin, args, source_info, label, run2, QtCore, QtGui, qt_renderer, traces, layout_capture, production_helper)
        roots[label] = (run1, run2)

    matrix = {}
    deterministic = True
    for profile in delegate.PROFILE_ORDER:
        rows = []
        for label in VARIANT_ORDER:
            row = copy_crop_and_metrics(args, label, roots[label][0], roots[label][1], profile, layout_capture)
            deterministic &= bool(row["CROP_DETERMINISTIC"] and row["FULL_PAGE_DETERMINISTIC"])
            rows.append(row)
        best = min(rows, key=lambda row: (float(row["MAE"]), float(row["CHANGED_RATIO"]), VARIANT_ORDER.index(row["VARIANT"])))
        matrix[profile] = {"VARIANTS": rows, "BEST": best}

    for profile in delegate.PROFILE_ORDER:
        matrix[profile]["SIDE_BY_SIDE"] = make_side_by_side(args, profile, matrix[profile]["BEST"], args.baseline_planner)

    unicode_payload = {}
    for profile in delegate.PROFILE_ORDER:
        text = traces[profile]["TEXT"]
        boundary = latin.boundary_trace(text, QtCore)
        qt_line_internal = [int(row["POSITION"]) for row in boundary["LINE"]["BOUNDARIES"] if 0 < int(row["POSITION"]) < len(text)]
        unicode_payload[profile] = {
            "TEXT": text,
            "CHARS": [
                {
                    "INDEX": index,
                    "CHAR": ch,
                    "CODEPOINT": f"U+{ord(ch):04X}",
                    "LINE_BREAK_CLASS": line_break_class(ch, regex),
                }
                for index, ch in enumerate(text)
            ],
            "QTEXTBOUNDARYFINDER_LINE": boundary["LINE"],
            "DEFAULT_UNICODE_INTERNAL_BREAKS": qt_line_internal,
            "DEFAULT_UNICODE_BREAK": "KEEP_TOGETHER" if not qt_line_internal else "BREAK_AVAILABLE",
            "DRAWINGML_OFFICE_TAILORED_BREAKS": traces[profile]["OFFICE_FILTERED_BREAK_POSITIONS"],
            "REFERENCE_RASTER_BEST_SEGMENTS": matrix[profile]["BEST"]["SEGMENTS"],
        }

    current_emergency = {profile: traces[profile]["CURRENT_EMERGENCY_SEGMENTS"] for profile in delegate.PROFILE_ORDER}
    best_segments = {profile: matrix[profile]["BEST"]["SEGMENTS"] for profile in delegate.PROFILE_ORDER}
    generic_segments = {profile: traces[profile]["FINAL_SEGMENTS"] for profile in delegate.PROFILE_ORDER}
    best_eq_emergency = all(best_segments[p] == current_emergency[p] for p in delegate.PROFILE_ORDER)
    best_eq_generic = all(best_segments[p] == generic_segments[p] for p in delegate.PROFILE_ORDER)

    baseline_rows = planner.current_rows(args.baseline_planner)
    control_root = roots[matrix[delegate.PROFILE_ORDER[0]]["BEST"]["VARIANT"]][0]
    control_rows = planner.current_rows(control_root)
    currency_preserved = all(int(control_rows[(p, "currency")].get("LINE_COUNT") or 0) == 2 for p in delegate.PROFILE_ORDER)
    unit_preserved = all(int(control_rows[(p, "unit")].get("LINE_COUNT") or 0) == 1 for p in delegate.PROFILE_ORDER)
    integer_preserved = all(planner.probe_sha(args.baseline_planner, p, "integer") == planner.probe_sha(control_root, p, "integer") for p in delegate.PROFILE_ORDER)
    name_preserved = all(planner.probe_sha(args.baseline_planner, p, "name") == planner.probe_sha(control_root, p, "name") for p in delegate.PROFILE_ORDER)

    early_return = {p: bool(traces[p]["EARLY_RETURN_SINGLE_LINE"]) for p in delegate.PROFILE_ORDER}
    default_unicode_keep = all(not unicode_payload[p]["DEFAULT_UNICODE_INTERNAL_BREAKS"] for p in delegate.PROFILE_ORDER)
    tailoring_needed = default_unicode_keep and any(len(best_segments[p]) > 1 for p in delegate.PROFILE_ORDER)
    generic_rule_possible = deterministic and best_eq_generic and unit_preserved and currency_preserved and integer_preserved and name_preserved
    ready = generic_rule_possible

    if all(not value for value in early_return.values()) and best_eq_generic:
        root_cause = "PREVIOUS PLANNER LINE_COUNT WAS A RASTER BAND/METRIC HARNESS ARTIFACT: generic planner already selected the best multi-segment DECIMAL split; no horizontalAdvance early return occurred"
    elif any(early_return.values()):
        root_cause = "EARLY SINGLE-LINE SHORT-CIRCUIT CONFIRMED"
    else:
        root_cause = "GENERIC PLANNER SEGMENTATION DIFFERS FROM REFERENCE-BEST SPLIT"

    (args.out / "planner-decision-trace.json").write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "decimal-segmentation-matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "decimal-current-emergency.json").write_text(json.dumps({"SEGMENTS": current_emergency, "GENERIC_PLANNER_SEGMENTS": generic_segments}, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "decimal-unicode-breaks.json").write_text(json.dumps(unicode_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "AFTER_SHA": AFTER_SHA,
        "PPTX_SHA256": PPTX_SHA,
        "DECIMAL_EARLY_RETURN": early_return,
        "DECIMAL_BREAK_CANDIDATES": {p: traces[p]["OFFICE_FILTERED_BREAK_POSITIONS"] for p in delegate.PROFILE_ORDER},
        "BEST_SEGMENTS": best_segments,
        "CURRENT_EMERGENCY_SEGMENTS": current_emergency,
        "GENERIC_PLANNER_SEGMENTS": generic_segments,
        "BEST_SEGMENTS_EQ_CURRENT_EMERGENCY": best_eq_emergency,
        "BEST_SEGMENTS_EQ_GENERIC_PLANNER": best_eq_generic,
        "DEFAULT_UNICODE_BEHAVIOR": "KEEP_NUMERIC_SEQUENCE_TOGETHER" if default_unicode_keep else "INTERNAL_LINE_BREAK_AVAILABLE",
        "OFFICE_REFERENCE_TAILORING_NEEDED": tailoring_needed,
        "CURRENCY_PRESERVED": currency_preserved,
        "UNIT_PRESERVED": unit_preserved,
        "INTEGER_PRESERVED": integer_preserved,
        "NAME_PRESERVED": name_preserved,
        "ALL_VARIANTS_DETERMINISTIC": deterministic,
        "ROOT_CAUSE": root_cause,
        "GENERIC_RULE_POSSIBLE": generic_rule_possible,
        "PRODUCTION_FILES_CHANGED": 0,
        "READY_TO_MODIFY_PR_111": ready,
    }
    (args.out / "decimal-planner-final-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
