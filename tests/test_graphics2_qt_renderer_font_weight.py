from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QGuiApplication

from srstudio.graphics2.qt_renderer import _set_font_weight


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


@pytest.mark.parametrize("requested", [100, 200, 300, 400, 500, 600, 700, 800, 900])
def test_renderer_preserves_standard_css_font_weights(requested):
    font = QFont("Arial")

    _set_font_weight(font, requested, __import__("PySide6.QtGui", fromlist=["QtGui"]))

    assert int(font.weight()) == requested


def test_renderer_font_weight_defaults_to_normal_and_clamps_outliers():
    QtGui = __import__("PySide6.QtGui", fromlist=["QtGui"])
    font = QFont("Arial")

    _set_font_weight(font, None, QtGui)
    assert int(font.weight()) == 400

    _set_font_weight(font, 950, QtGui)
    assert int(font.weight()) == 900

    _set_font_weight(font, 50, QtGui)
    assert int(font.weight()) == 100
