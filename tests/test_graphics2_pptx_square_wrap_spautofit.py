from __future__ import annotations

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
