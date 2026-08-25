from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path


def _render_font(style: dict, QtGui, qt_renderer):
    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
    base_size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    logical_px = base_size * (96.0 / 72.0) if unit in {"pt", "point", "points"} else base_size
    font = QtGui.QFont(family)
    font.setPixelSize(max(1, round(logical_px)))
    qt_renderer._set_font_weight(font, style.get("font_weight"), QtGui)
    font.setItalic(bool(style.get("italic")))
    if style.get("letter_spacing") not in (None, ""):
        font.setLetterSpacing(
            QtGui.QFont.AbsoluteSpacing,
            float(style.get("letter_spacing") or 0.0),
        )
    return font, logical_px


def _connected_components(mask):
    import numpy as np

    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    components: list[dict] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            while stack:
                cy, cx = stack.pop()
                area += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        ny = cy + dy
                        nx = cx + dx
                        if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            components.append(
                {
                    "BBOX": [min_x, min_y, max_x + 1, max_y + 1],
                    "AREA": area,
                }
            )
    components.sort(key=lambda item: (item["BBOX"][1], item["BBOX"][0]))
    return components


def _active_row_bands(mask):
    import numpy as np

    rows = np.where(mask.any(axis=1))[0]
    if not len(rows):
        return []
    bands = []
    start = prev = int(rows[0])
    for raw in rows[1:]:
        value = int(raw)
        if value > prev + 1:
            bands.append([start, prev + 1])
            start = value
        prev = value
    bands.append([start, prev + 1])
    return bands


def _qtextlayout_trace(text: str, rect, style: dict, render_font, QtCore, QtGui, qt_renderer):
    layout_font = qt_renderer._pptx_source_layout_font(style, render_font, QtGui)
    layout = QtGui.QTextLayout(text, layout_font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    raw_lines: list[dict] = []
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            configured = max(0.1, float(rect.width()))
            line.setLineWidth(configured)
            start = int(line.textStart())
            length = int(line.textLength())
            fragment = text[start : start + length]
            raw_lines.append(
                {
                    "START": start,
                    "LENGTH": length,
                    "TEXT": fragment,
                    "NATURAL_TEXT_WIDTH": float(line.naturalTextWidth()),
                    "LINE_WIDTH_CONFIGURED": configured,
                }
            )
    finally:
        layout.endLayout()

    draw_metrics = QtGui.QFontMetricsF(render_font)
    line_advance = qt_renderer._pptx_wrapped_line_advance(style, draw_metrics)
    first_baseline = None
    if raw_lines:
        tight = draw_metrics.tightBoundingRect(raw_lines[0]["TEXT"])
        first_baseline = float(rect.top()) - float(tight.top())
    horizontal = str(style.get("align") or "center").lower()
    for index, row in enumerate(raw_lines):
        fragment = row["TEXT"]
        source_advance = float(QtGui.QFontMetricsF(layout_font).horizontalAdvance(fragment))
        render_advance = float(draw_metrics.horizontalAdvance(fragment))
        if horizontal in {"left", "l"}:
            x = float(rect.left())
        elif horizontal in {"right", "r"}:
            x = float(rect.right()) - render_advance
        else:
            x = float(rect.left()) + (float(rect.width()) - render_advance) * 0.5
        row.update(
            {
                "HORIZONTAL_ADVANCE": source_advance,
                "RENDER_HORIZONTAL_ADVANCE": render_advance,
                "X": x,
                "BASELINE": None if first_baseline is None else first_baseline + line_advance * index,
            }
        )
    return raw_lines


def _trace_layout(text: str, rect, style: dict, render_font, QtCore, QtGui, qt_renderer):
    render_metrics = QtGui.QFontMetricsF(render_font)
    source_font = qt_renderer._pptx_source_layout_font(style, render_font, QtGui)
    source_metrics = QtGui.QFontMetricsF(source_font)
    render_advance = float(render_metrics.horizontalAdvance(text))
    source_advance = float(source_metrics.horizontalAdvance(text))
    source_width = float(qt_renderer._pptx_source_layout_width(text, style, render_font, QtGui))
    overflow_delta = source_width - float(rect.width())
    overflow = source_width > float(rect.width()) + 0.01
    effective_wrap = str(qt_renderer._pptx_effective_wrap(style))
    explicit = qt_renderer._explicit_multiline_layout(text, rect, style, render_font, QtCore, QtGui)
    semantic_eligible = (
        bool(text)
        and "\n" not in text.replace("\r\n", "\n").replace("\r", "\n")
        and str(style.get("pptx_auto_fit") or "").lower() == "shape"
        and not qt_renderer._should_fit_text(style)
        and str(style.get("v_align") or style.get("vertical_align") or "center").lower() in {"top", "t"}
        and effective_wrap == "square"
    )
    wrapped_called = explicit is None
    wrapped = None
    if wrapped_called:
        wrapped = qt_renderer._pptx_shape_autofit_wrapped_layout(
            text, rect, style, render_font, QtCore, QtGui
        )
    shape = None
    if explicit is None and wrapped is None:
        shape = qt_renderer._pptx_shape_autofit_single_line_layout(
            text, rect, style, render_font, QtGui
        )
    if explicit is not None:
        route = "explicit_multiline"
    elif wrapped is not None:
        route = "pptx_shape_autofit_wrapped"
    elif shape is not None:
        route = "shape_autofit_explicit_baseline"
    else:
        route = "qrect_native"

    qtext_lines = []
    if semantic_eligible and overflow:
        qtext_lines = _qtextlayout_trace(
            text, rect, style, render_font, QtCore, QtGui, qt_renderer
        )

    return {
        "RENDER_HORIZONTAL_ADVANCE": render_advance,
        "SOURCE_LAYOUT_HORIZONTAL_ADVANCE": source_advance,
        "SOURCE_LAYOUT_WIDTH": source_width,
        "RECT_WIDTH": float(rect.width()),
        "RECT_HEIGHT": float(rect.height()),
        "SOURCE_LAYOUT_MINUS_RECT": overflow_delta,
        "OVERFLOW_PREDICATE": overflow,
        "EFFECTIVE_WRAP": effective_wrap,
        "EXPLICIT_MULTILINE_SELECTED": explicit is not None,
        "PPTX_WRAPPED_SEMANTIC_ELIGIBLE": semantic_eligible,
        "PPTX_WRAPPED_ELIGIBLE": semantic_eligible and overflow,
        "PPTX_WRAPPED_CALLED": wrapped_called,
        "PPTX_WRAPPED_RETURNED_NONE": wrapped is None,
        "PPTX_WRAPPED_LINE_COUNT": 0 if wrapped is None else len(wrapped),
        "PPTX_WRAPPED_LINES": []
        if wrapped is None
        else [
            {"TEXT": str(line), "X": float(x), "BASELINE": float(baseline)}
            for line, x, baseline in wrapped
        ],
        "SINGLE_LINE_SELECTED": shape is not None,
        "FINAL_LAYOUT_ROUTE": route,
        "QTEXTLAYOUT_EXECUTED": bool(qtext_lines),
        "QTEXTLAYOUT_LINE_COUNT": len(qtext_lines),
        "QTEXTLAYOUT_LINES": qtext_lines,
    }


def _enhance_probe(original_probe):
    def enhanced(node, qt_renderer, QtCore, QtGui, out_path: Path) -> dict:
        from PIL import Image
        import numpy as np

        result = original_probe(node, qt_renderer, QtCore, QtGui, out_path)
        style = node.style
        rect = node.rect.normalized()
        render_font, logical_px = _render_font(style, QtGui, qt_renderer)
        local_rect = QtCore.QRectF(0.0, 0.0, rect.width, rect.height)
        text = str(node.text or "")
        trace = _trace_layout(
            text, local_rect, style, render_font, QtCore, QtGui, qt_renderer
        )

        arr = np.asarray(Image.open(out_path).convert("RGB"))
        mask = np.max(arr, axis=2) > 32
        components = _connected_components(mask)
        active_bands = _active_row_bands(mask)
        result.update(
            {
                "NODE_ID": str(node.id),
                "TEXT_REPR_PROBE": repr(text),
                "FONT_FAMILY": str(style.get("font_family") or style.get("source_font_family") or "Segoe UI"),
                "FONT_SIZE_SOURCE_PT": float(style.get("font_size") or 0.0),
                "FONT_SIZE_RENDER_LOGICAL_PX": float(logical_px),
                "FONT_SIZE_RENDER_PIXEL_SIZE": int(render_font.pixelSize()),
                "LETTER_SPACING": style.get("letter_spacing"),
                "LETTER_SPACING_PT": style.get("letter_spacing_pt"),
                "PPTX_AUTO_FIT": style.get("pptx_auto_fit"),
                "PPTX_WRAP": style.get("pptx_wrap"),
                "NOWRAP": bool(style.get("nowrap")),
                "FIT_INSIDE_BOX": bool(style.get("fit_inside_box")),
                "V_ALIGN": style.get("v_align") or style.get("vertical_align"),
                "LINE_SPACING_PT": style.get("line_spacing_pt"),
                "LINE_SPACING_PX": style.get("line_spacing_px"),
                "LINE_SPACING_PERCENT": style.get("line_spacing_percent"),
                "RASTER_ACTIVE_ROW_BANDS": active_bands,
                "RASTER_ACTIVE_ROW_BAND_COUNT": len(active_bands),
                "RASTER_CONNECTED_COMPONENTS": components,
                "RASTER_CONNECTED_COMPONENT_COUNT": len(components),
                **trace,
            }
        )
        return result

    return enhanced


def _generic_decimal_trace(QtCore, QtGui, qt_renderer):
    text = ",86"
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
    }
    metrics = QtGui.QFontMetricsF(font)
    widest = max(float(metrics.horizontalAdvance(ch)) for ch in text)
    full = float(metrics.horizontalAdvance(text))
    rect = QtCore.QRectF(10.0, 20.0, max(widest + 0.25, full * 0.58), 8.0)
    trace = _trace_layout(text, rect, style, font, QtCore, QtGui, qt_renderer)
    return {
        "PROFILE": "generic",
        "ROLE": "decimal",
        "TEXT_REPR": repr(text),
        "FONT_FAMILY": "Arial",
        "FONT_SIZE_SOURCE_PT": 13.5,
        "FONT_SIZE_RENDER_LOGICAL_PX": 18.0,
        "FONT_SIZE_RENDER_PIXEL_SIZE": 18,
        "LETTER_SPACING": None,
        "LETTER_SPACING_PT": None,
        "PPTX_AUTO_FIT": "shape",
        "PPTX_WRAP": "square",
        "NOWRAP": False,
        "FIT_INSIDE_BOX": False,
        "V_ALIGN": "top",
        "LINE_SPACING_PT": None,
        "LINE_SPACING_PX": None,
        "LINE_SPACING_PERCENT": None,
        **trace,
    }


def _classify(real: dict) -> str:
    if (
        str(real.get("PPTX_WRAP") or "").lower() != "square"
        or bool(real.get("NOWRAP"))
        or str(real.get("PPTX_AUTO_FIT") or "").lower() != "shape"
    ):
        return "A — WRAP CONTRACT NOT MATERIALIZED"
    if not bool(real.get("OVERFLOW_PREDICATE")):
        return "B — OVERFLOW PREDICATE FALSE"
    if bool(real.get("PPTX_WRAPPED_RETURNED_NONE")):
        if bool(real.get("QTEXTLAYOUT_EXECUTED")) and int(real.get("QTEXTLAYOUT_LINE_COUNT") or 0) <= 1:
            return "C — QTEXTLAYOUT CALLED BUT DID NOT BREAK"
        return "E — OTHER"
    if int(real.get("PPTX_WRAPPED_LINE_COUNT") or 0) > 1 and int(real.get("LINE_COUNT") or 0) <= 1:
        return "D — WRAPPED ROUTE WORKED; COMPARATOR WRONG"
    return "E — OTHER"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delegate", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    delegate_path = args.delegate.resolve()
    spec = importlib.util.spec_from_file_location("quinta3_text_delegate", delegate_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load delegate: {delegate_path}")
    delegate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(delegate)
    original_probe = delegate.draw_text_probe
    delegate.draw_text_probe = _enhance_probe(original_probe)

    previous_argv = sys.argv[:]
    sys.argv = [
        str(delegate_path),
        "--pptx",
        str(args.pptx),
        "--source-root",
        str(args.source_root),
        "--reference",
        str(args.reference),
        "--out",
        str(args.out),
    ]
    try:
        result = int(delegate.main())
    finally:
        sys.argv = previous_argv
    if result != 0:
        return result

    from PySide6 import QtCore, QtGui
    from srstudio.graphics2 import qt_renderer

    metrics_path = args.out / "text-variant-metrics.json"
    rows = json.loads(metrics_path.read_text(encoding="utf-8"))
    current = [
        row
        for row in rows
        if row.get("VARIANT") == "current" and row.get("ROLE") in {"currency", "decimal"}
    ]
    current.sort(key=lambda row: (str(row.get("PROFILE")), str(row.get("ROLE"))))
    if len(current) != 8:
        raise RuntimeError(f"Expected 8 current CURRENCY/DECIMAL traces, got {len(current)}")

    generic = _generic_decimal_trace(QtCore, QtGui, qt_renderer)
    costela = next(
        row for row in current if row.get("PROFILE") == "costela" and row.get("ROLE") == "decimal"
    )
    difference_fields = (
        "RECT_WIDTH",
        "FONT_FAMILY",
        "FONT_SIZE_SOURCE_PT",
        "FONT_SIZE_RENDER_PIXEL_SIZE",
        "LETTER_SPACING",
        "LETTER_SPACING_PT",
        "SOURCE_LAYOUT_HORIZONTAL_ADVANCE",
        "SOURCE_LAYOUT_WIDTH",
        "PPTX_WRAP",
        "PPTX_AUTO_FIT",
        "NOWRAP",
        "FIT_INSIDE_BOX",
        "V_ALIGN",
        "LINE_SPACING_PT",
        "LINE_SPACING_PX",
        "OVERFLOW_PREDICATE",
        "PPTX_WRAPPED_LINE_COUNT",
        "QTEXTLAYOUT_LINE_COUNT",
    )
    differences = {
        field: {"GENERIC": generic.get(field), "REAL": costela.get(field)}
        for field in difference_fields
        if generic.get(field) != costela.get(field)
    }
    classification = _classify(costela)

    route_payload = {
        "SOURCE_SHA": str(args.source_root.resolve()),
        "TARGET_COUNT": 8,
        "NODES": current,
    }
    overflow_payload = {
        "NODES": [
            {
                "PROFILE": row["PROFILE"],
                "ROLE": row["ROLE"],
                "TEXT_REPR": row["TEXT_REPR"],
                "RECT_WIDTH": row["RECT_WIDTH"],
                "RENDER_HORIZONTAL_ADVANCE": row["RENDER_HORIZONTAL_ADVANCE"],
                "SOURCE_LAYOUT_HORIZONTAL_ADVANCE": row["SOURCE_LAYOUT_HORIZONTAL_ADVANCE"],
                "SOURCE_LAYOUT_WIDTH": row["SOURCE_LAYOUT_WIDTH"],
                "SOURCE_LAYOUT_MINUS_RECT": row["SOURCE_LAYOUT_MINUS_RECT"],
                "OVERFLOW_PREDICATE": row["OVERFLOW_PREDICATE"],
            }
            for row in current
        ]
    }
    summary = {
        "ROOT_CAUSE_CLASS": classification,
        "GENERIC_DECIMAL_TEST": generic,
        "COSTELA_DECIMAL_REAL": costela,
        "DIFFERENCE_GENERIC_VS_REAL": differences,
        "CURRENCY_ROUTES": {
            row["PROFILE"]: row["FINAL_LAYOUT_ROUTE"]
            for row in current
            if row["ROLE"] == "currency"
        },
        "DECIMAL_ROUTES": {
            row["PROFILE"]: row["FINAL_LAYOUT_ROUTE"]
            for row in current
            if row["ROLE"] == "decimal"
        },
        "CONTRACT_MATERIALIZATION": {
            f"{row['PROFILE']}/{row['ROLE']}": {
                "PPTX_WRAP": row.get("PPTX_WRAP"),
                "NOWRAP": row.get("NOWRAP"),
                "PPTX_AUTO_FIT": row.get("PPTX_AUTO_FIT"),
                "LINE_SPACING_PT": row.get("LINE_SPACING_PT"),
                "LINE_SPACING_PX": row.get("LINE_SPACING_PX"),
            }
            for row in current
        },
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "wrap-route-trace.json").write_text(
        json.dumps(route_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out / "overflow-trace.json").write_text(
        json.dumps(overflow_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out / "wrap-route-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== COSTELA DECIMAL REAL ===")
    for key in (
        "PPTX_WRAP",
        "NOWRAP",
        "PPTX_AUTO_FIT",
        "RECT_WIDTH",
        "SOURCE_LAYOUT_WIDTH",
        "SOURCE_LAYOUT_MINUS_RECT",
        "OVERFLOW_PREDICATE",
        "PPTX_WRAPPED_CALLED",
        "PPTX_WRAPPED_RETURNED_NONE",
        "PPTX_WRAPPED_LINE_COUNT",
        "FINAL_LAYOUT_ROUTE",
        "QTEXTLAYOUT_LINE_COUNT",
        "LINE_COUNT",
        "RASTER_ACTIVE_ROW_BAND_COUNT",
        "RASTER_CONNECTED_COMPONENT_COUNT",
    ):
        print(f"{key}={costela.get(key)}")
    print("=== GENERIC DECIMAL TEST ===")
    for key in (
        "RECT_WIDTH",
        "SOURCE_LAYOUT_WIDTH",
        "SOURCE_LAYOUT_MINUS_RECT",
        "OVERFLOW_PREDICATE",
        "PPTX_WRAPPED_LINE_COUNT",
        "FINAL_LAYOUT_ROUTE",
        "QTEXTLAYOUT_LINE_COUNT",
    ):
        print(f"{key}={generic.get(key)}")
    print(f"ROOT_CAUSE_CLASS={classification}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
