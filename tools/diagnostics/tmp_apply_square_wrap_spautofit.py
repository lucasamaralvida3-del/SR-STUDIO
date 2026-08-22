from __future__ import annotations

from pathlib import Path

BASE_SHA = "21dda44fe758a2899b4c15ffa041b2e0f6ff6d33"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, got {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    renderer = Path("src/srstudio/graphics2/qt_renderer.py")
    full_card = Path("src/srstudio/graphics2/slot_corpus_full_card.py")

    replace_once(
        renderer,
        '''    shape_layout = _pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui)\n    if shape_layout is not None:\n        x, baseline = shape_layout\n        painter.drawText(QtCore.QPointF(x, baseline), text)\n        return\n''',
        '''    wrapped_layout = _pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui)\n    if wrapped_layout is not None:\n        for line, x, baseline in wrapped_layout:\n            painter.drawText(QtCore.QPointF(x, baseline), line)\n        return\n    shape_layout = _pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui)\n    if shape_layout is not None:\n        x, baseline = shape_layout\n        painter.drawText(QtCore.QPointF(x, baseline), text)\n        return\n''',
    )

    replace_once(
        renderer,
        '''    metrics = QtGui.QFontMetricsF(font)\n    advance = float(metrics.horizontalAdvance(normalized))\n    tight = metrics.tightBoundingRect(normalized)\n''',
        '''    metrics = QtGui.QFontMetricsF(font)\n    advance = float(metrics.horizontalAdvance(normalized))\n    if (\n        _pptx_effective_wrap(style) == "square"\n        and not bool(style.get("nowrap", False))\n        and _pptx_source_layout_width(normalized, style, font, QtGui) > float(rect.width()) + 0.01\n    ):\n        return None\n    tight = metrics.tightBoundingRect(normalized)\n''',
    )

    marker = '''\n\ndef _set_font_weight(font, value: object, QtGui) -> None:\n'''
    helper = r'''

def _pptx_effective_wrap(style: dict) -> str:
    """Return the explicit DrawingML wrapping contract carried by the scene.

    ``bodyPr@wrap`` defaults to ``square`` in DrawingML, but legacy scene
    objects did not preserve whether that semantic was known or merely implied
    by ``nowrap=False``.  Only an explicit ``pptx_wrap`` value opts the
    shape-autofit path into DrawingML wrapping; ``nowrap=True`` always wins.
    """

    if bool(style.get("nowrap", False)):
        return "none"
    value = str(style.get("pptx_wrap") or "").strip().lower()
    if value in {"square", "wrap", "wordwrap", "word_wrap"}:
        return "square"
    if value in {"none", "nowrap", "no_wrap"}:
        return "none"
    return ""


def _pptx_source_layout_font(style: dict, font, QtGui):
    """Use the unrounded source point size for line-break decisions only.

    Rendering keeps the established #106 pixel-sized QFont so text that fits
    remains byte-for-byte on the explicit-baseline path.  DrawingML line
    breaking, however, is based on the source point size and must not silently
    inherit the integer pixel rounding used by QPainter output.
    """

    unit = str(style.get("font_size_unit") or "pt").strip().lower()
    if unit not in {"pt", "point", "points"}:
        return font
    try:
        source_pt = float(style.get("font_size") or 0.0)
    except (TypeError, ValueError):
        return font
    if source_pt <= 0.0:
        return font
    result = QtGui.QFont(font)
    result.setPointSizeF(source_pt)
    return result


def _pptx_source_layout_width(text: str, style: dict, font, QtGui) -> float:
    layout_font = _pptx_source_layout_font(style, font, QtGui)
    metrics = QtGui.QFontMetricsF(layout_font)
    return max(float(metrics.horizontalAdvance(text)), float(metrics.tightBoundingRect(text).width()))


def _pptx_wrapped_line_advance(style: dict, metrics) -> float:
    if style.get("line_spacing_px") not in (None, ""):
        try:
            value = float(style.get("line_spacing_px") or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.0:
            return value
    if style.get("line_spacing_percent") not in (None, ""):
        try:
            percent = float(style.get("line_spacing_percent") or 0.0)
        except (TypeError, ValueError):
            percent = 0.0
        if percent > 0.0:
            return float(metrics.height()) * percent / 100.0
    return float(metrics.lineSpacing())


def _pptx_shape_autofit_wrapped_layout(text: str, rect, style: dict, font, QtCore, QtGui):
    """Lay out DrawingML ``wrap=square`` + ``spAutoFit`` text when it overflows.

    QTextLayout provides normal word wrapping and the DrawingML-required
    emergency character fallback for tokens with no usable boundary.  The
    helper is deliberately inactive while the source text fits horizontally,
    preserving the #106 explicit-baseline route for ordinary one-line text.
    ``spAutoFit`` is shape-growth semantics, so wrapped baselines are not
    clipped to the stale source xfrm height.
    """

    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized or "\n" in normalized:
        return None
    if str(style.get("pptx_auto_fit") or "").lower() != "shape":
        return None
    if _should_fit_text(style):
        return None
    vertical = str(style.get("v_align") or style.get("vertical_align") or "center").lower()
    if vertical not in {"top", "t"}:
        return None
    if _pptx_effective_wrap(style) != "square":
        return None

    layout_font = _pptx_source_layout_font(style, font, QtGui)
    layout_metrics = QtGui.QFontMetricsF(layout_font)
    source_width = max(
        float(layout_metrics.horizontalAdvance(normalized)),
        float(layout_metrics.tightBoundingRect(normalized).width()),
    )
    if source_width <= float(rect.width()) + 0.01:
        return None

    layout = QtGui.QTextLayout(normalized, layout_font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    fragments: list[str] = []
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(0.1, float(rect.width())))
            start = int(line.textStart())
            length = int(line.textLength())
            fragment = normalized[start : start + length]
            if fragment:
                fragments.append(fragment)
    finally:
        layout.endLayout()
    if len(fragments) <= 1:
        return None

    draw_metrics = QtGui.QFontMetricsF(font)
    line_advance = _pptx_wrapped_line_advance(style, draw_metrics)
    horizontal = str(style.get("align") or "center").lower()
    first_tight = draw_metrics.tightBoundingRect(fragments[0])
    first_baseline = float(rect.top()) - float(first_tight.top())
    result: list[tuple[str, float, float]] = []
    for index, fragment in enumerate(fragments):
        advance = float(draw_metrics.horizontalAdvance(fragment))
        if horizontal in {"left", "l"}:
            x = float(rect.left())
        elif horizontal in {"right", "r"}:
            x = float(rect.right()) - advance
        else:
            x = float(rect.left()) + (float(rect.width()) - advance) * 0.5
        result.append((fragment, x, first_baseline + line_advance * index))
    return result
'''
    text = renderer.read_text(encoding="utf-8")
    if marker not in text:
        raise RuntimeError("renderer helper insertion marker missing")
    renderer.write_text(text.replace(marker, helper + marker, 1), encoding="utf-8")

    old_style = '''def _text_style(size: float, spacing_pt: float) -> dict[str, Any]:\n    return {\n        "font_family": "Anton",\n        "source_font_family": "Anton",\n        "font_size": float(size),\n        "font_size_unit": "pt",\n        "font_weight": 400,\n        "color": "#FFFFFF",\n        "fill": "#FFFFFF",  # backward-compatible metadata; renderer/QML use color.\n        "align": "center",\n        "v_align": "top",\n        "fit_inside_box": False,\n        "nowrap": True,\n        "letter_spacing_pt": float(spacing_pt),\n        "letter_spacing": float(spacing_pt) * (96.0 / 72.0),\n        "pptx_auto_fit": "shape",\n        "text_insets": {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},\n    }\n'''
    new_style = '''def _text_style(size: float, spacing_pt: float, *, line_spacing_pt: float | None = None) -> dict[str, Any]:\n    style: dict[str, Any] = {\n        "font_family": "Anton",\n        "source_font_family": "Anton",\n        "font_size": float(size),\n        "font_size_unit": "pt",\n        "font_weight": 400,\n        "color": "#FFFFFF",\n        "fill": "#FFFFFF",  # backward-compatible metadata; renderer/QML use color.\n        "align": "center",\n        "v_align": "top",\n        "fit_inside_box": False,\n        # DrawingML bodyPr@wrap is omitted in the exact source, whose effective\n        # value is square. Preserve that semantic explicitly instead of using\n        # the legacy ambiguous nowrap contract.\n        "nowrap": False,\n        "pptx_wrap": "square",\n        "letter_spacing_pt": float(spacing_pt),\n        "letter_spacing": float(spacing_pt) * (96.0 / 72.0),\n        "pptx_auto_fit": "shape",\n        "text_insets": {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},\n    }\n    if line_spacing_pt is not None:\n        style["line_spacing_pt"] = float(line_spacing_pt)\n        style["line_spacing_px"] = float(line_spacing_pt) * (96.0 / 72.0)\n    return style\n'''
    replace_once(full_card, old_style, new_style)

    text = full_card.read_text(encoding="utf-8")
    currency_old = '"style": _text_style(9.22, -0.26)'
    decimal_old = '"style": _text_style(7.80, -0.22)'
    if text.count(currency_old) != 4 or text.count(decimal_old) != 4:
        raise RuntimeError("expected four currency and four decimal style calls")
    text = text.replace(currency_old, '"style": _text_style(9.22, -0.26, line_spacing_pt=9.96)')
    text = text.replace(decimal_old, '"style": _text_style(7.80, -0.22, line_spacing_pt=8.42)')
    full_card.write_text(text, encoding="utf-8")

    Path("tests/test_graphics2_pptx_square_wrap_spautofit.py").write_text(r'''from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from srstudio.graphics2.qt_renderer import (
    _pptx_shape_autofit_single_line_layout,
    _pptx_shape_autofit_wrapped_layout,
)


@pytest.fixture(scope="module")
def qt():
    from PySide6 import QtCore, QtGui
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    return QtCore, QtGui, app


def _font(QtGui, px: int = 18):
    font = QtGui.QFont("Arial")
    font.setPixelSize(px)
    return font


def _style(**overrides):
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
    style.update(overrides)
    return style


def _narrow_rect(text: str, font, QtCore, QtGui):
    metrics = QtGui.QFontMetricsF(font)
    widest = max(float(metrics.horizontalAdvance(ch)) for ch in text)
    full = float(metrics.horizontalAdvance(text))
    assert full > widest
    return QtCore.QRectF(10.0, 20.0, max(widest + 0.25, full * 0.58), 8.0)


def test_square_shape_autofit_wraps_narrow_currency_without_manual_break(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    rect = _narrow_rect("R$", font, QtCore, QtGui)
    layout = _pptx_shape_autofit_wrapped_layout("R$", rect, _style(), font, QtCore, QtGui)
    assert layout is not None
    assert len(layout) > 1
    assert "".join(line for line, _, _ in layout) == "R$"


def test_square_shape_autofit_emergency_wraps_decimal_without_boundary(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    rect = _narrow_rect(",86", font, QtCore, QtGui)
    layout = _pptx_shape_autofit_wrapped_layout(",86", rect, _style(), font, QtCore, QtGui)
    assert layout is not None
    assert len(layout) > 1
    assert "".join(line for line, _, _ in layout) == ",86"


def test_square_shape_autofit_that_fits_stays_on_explicit_baseline(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    metrics = QtGui.QFontMetricsF(font)
    rect = QtCore.QRectF(0.0, 0.0, float(metrics.horizontalAdvance("24")) + 8.0, 8.0)
    style = _style(font_size=18.0, font_size_unit="px")
    assert _pptx_shape_autofit_wrapped_layout("24", rect, style, font, QtCore, QtGui) is None
    assert _pptx_shape_autofit_single_line_layout("24", rect, style, font, QtGui) is not None


def test_nowrap_overflow_stays_single_line(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    rect = _narrow_rect("R$", font, QtCore, QtGui)
    style = _style(nowrap=True)
    assert _pptx_shape_autofit_wrapped_layout("R$", rect, style, font, QtCore, QtGui) is None
    assert _pptx_shape_autofit_single_line_layout("R$", rect, style, font, QtGui) is not None


@pytest.mark.parametrize("text", ["24", "KG"])
def test_fitting_integer_and_unit_like_text_preserve_explicit_baseline(text, qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    metrics = QtGui.QFontMetricsF(font)
    rect = QtCore.QRectF(0.0, 0.0, float(metrics.horizontalAdvance(text)) + 6.0, 7.0)
    style = _style(font_size=18.0, font_size_unit="px")
    assert _pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui) is None
    assert _pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui) is not None


def test_wrapped_layout_uses_explicit_drawingml_line_spacing(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    rect = _narrow_rect("R$", font, QtCore, QtGui)
    layout = _pptx_shape_autofit_wrapped_layout(
        "R$", rect, _style(line_spacing_px=13.28), font, QtCore, QtGui
    )
    assert layout is not None and len(layout) >= 2
    assert layout[1][2] - layout[0][2] == pytest.approx(13.28)
''', encoding="utf-8")

    Path("tests/test_graphics2_quinta3_meat_text_wrap_contract.py").write_text(r'''from __future__ import annotations

import pytest

from srstudio.graphics2.slot_corpus_full_card import MEAT_STRIP_FULL_CARD_PROFILES


def test_exact_meat_strip_wrap_contract_is_square_not_nowrap():
    for profile in MEAT_STRIP_FULL_CARD_PROFILES.values():
        for role in ("name", "currency", "integer", "decimal", "unit"):
            style = profile["roles"][role]["style"]
            assert style["pptx_wrap"] == "square"
            assert style["nowrap"] is False


def test_exact_meat_strip_multiline_roles_preserve_source_line_spacing_only_where_needed():
    for profile in MEAT_STRIP_FULL_CARD_PROFILES.values():
        currency = profile["roles"]["currency"]["style"]
        decimal = profile["roles"]["decimal"]["style"]
        assert currency["line_spacing_pt"] == pytest.approx(9.96)
        assert currency["line_spacing_px"] == pytest.approx(9.96 * 96.0 / 72.0)
        assert decimal["line_spacing_pt"] == pytest.approx(8.42)
        assert decimal["line_spacing_px"] == pytest.approx(8.42 * 96.0 / 72.0)
        for role in ("name", "integer", "unit"):
            assert "line_spacing_pt" not in profile["roles"][role]["style"]
            assert "line_spacing_px" not in profile["roles"][role]["style"]
''', encoding="utf-8")

    # Keep the existing #106 regression untouched and remove temporary tooling
    # from the final production diff.
    Path("tools/diagnostics/tmp_apply_square_wrap_spautofit.py").unlink(missing_ok=True)
    Path(".github/workflows/tmp-apply-square-wrap-spautofit.yml").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
