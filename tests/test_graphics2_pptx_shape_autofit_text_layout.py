from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui
from PySide6.QtGui import QFont, QFontMetricsF, QGuiApplication

from srstudio.graphics2.qt_renderer import _pptx_shape_autofit_single_line_layout


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def test_pptx_shape_autofit_top_anchor_uses_explicit_baseline_without_meat_contract():
    font = QFont("Arial")
    font.setPixelSize(29)
    rect = QtCore.QRectF(100.0, 50.0, 24.0, 26.0)
    style = {
        "pptx_auto_fit": "shape",
        "fit_inside_box": False,
        "align": "center",
        "v_align": "top",
        "nowrap": True,
    }

    layout = _pptx_shape_autofit_single_line_layout("24", rect, style, font, QtGui)

    assert layout is not None
    x, baseline = layout
    metrics = QFontMetricsF(font)
    tight = metrics.tightBoundingRect("24")
    advance = metrics.horizontalAdvance("24")
    assert x == pytest.approx(rect.left() + (rect.width() - advance) * 0.5)
    assert baseline + tight.top() == pytest.approx(rect.top())
    assert metrics.height() > rect.height()


@pytest.mark.parametrize(
    ("text", "style"),
    [
        ("24", {"align": "center", "v_align": "top"}),
        ("24", {"pptx_auto_fit": "shape", "fit_inside_box": True, "v_align": "top"}),
        ("24", {"pptx_auto_fit": "shape", "fit_inside_box": False, "v_align": "center"}),
        ("24\n86", {"pptx_auto_fit": "shape", "fit_inside_box": False, "v_align": "top"}),
    ],
)
def test_pptx_shape_autofit_explicit_baseline_is_narrowly_scoped(text, style):
    font = QFont("Arial")
    font.setPixelSize(20)
    rect = QtCore.QRectF(0.0, 0.0, 80.0, 20.0)

    assert _pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui) is None
