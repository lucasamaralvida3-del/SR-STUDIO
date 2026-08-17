from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore
from PySide6.QtGui import QFont, QFontMetricsF, QGuiApplication, QImage

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.qt_renderer import _text_flags, render_pdf, render_png


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def _document() -> GraphicsDocument:
    document = GraphicsDocument(name="Graphics 2 Render Smoke")
    page = document.active_page
    page.width = 600
    page.height = 800
    page.background = "#FFFFFF"
    page.add_node(
        GraphicsNode(
            kind=NodeKind.RECT,
            name="Card",
            transform=Transform(x=50, y=60, width=500, height=300),
            style={"fill": "#F8FAFC", "stroke": "#1D4ED8", "stroke_width": 3, "radius": 18},
        )
    )
    page.add_node(
        GraphicsNode(
            kind=NodeKind.TEXT,
            name="Nome",
            text="ACÉM BOVINO",
            transform=Transform(x=80, y=90, width=440, height=70),
            style={
                "font_family": "Arial",
                "font_size": 28,
                "font_size_unit": "pt",
                "font_weight": 800,
                "align": "center",
                "v_align": "center",
                "fit_inside_box": True,
            },
        )
    )
    page.add_node(
        GraphicsNode(
            kind=NodeKind.TEXT,
            name="Preço",
            text="128",
            transform=Transform(x=160, y=180, width=230, height=140),
            style={
                "font_family": "Arial",
                "font_size": 86,
                "font_size_unit": "pt",
                "font_weight": 900,
                "align": "right",
                "v_align": "center",
                "nowrap": True,
                "fit_inside_box": True,
            },
        )
    )
    return document


def _effects_document() -> GraphicsDocument:
    document = GraphicsDocument(name="DrawingML effects")
    page = document.active_page
    page.width = 220
    page.height = 120
    page.background = "#FFFFFF"
    page.add_node(
        GraphicsNode(
            id="gradient-card",
            kind=NodeKind.RECT,
            name="Gradient Card",
            transform=Transform(x=40, y=30, width=120, height=60),
            style={
                "fill": "#FFFFFF",
                "gradient": {
                    "type": "linear",
                    "angle": 0.0,
                    "stops": [
                        {"position": 0.0, "color": "#FF0000", "alpha": 1.0},
                        {"position": 1.0, "color": "#0000FF", "alpha": 1.0},
                    ],
                },
                "shadow": {
                    "type": "outer",
                    "color": "#000000",
                    "alpha": 0.9,
                    "blur": 0.0,
                    "distance": 18.0,
                    "direction": 0.0,
                    "rot_with_shape": False,
                },
            },
        )
    )
    return document


def test_qt_renderer_exports_high_resolution_png(tmp_path):
    report = render_png(_document(), tmp_path / "page.png", target_width=1800)
    assert report.ok
    assert report.width == 1800
    assert report.height == 2400
    assert report.output.stat().st_size > 10_000


def test_qt_renderer_exports_pdf(tmp_path):
    report = render_pdf(_document(), tmp_path / "page.pdf", dpi=300)
    assert report.ok
    assert report.pages == 1
    assert report.output.read_bytes().startswith(b"%PDF")


def test_qpainter_nowrap_preserves_explicit_newlines():
    font = QFont("Arial")
    font.setPixelSize(28)
    metrics = QFontMetricsF(font)
    rect = QtCore.QRectF(0, 0, 400, 300)
    flags = _text_flags({"nowrap": True, "align": "left", "v_align": "top"}, QtCore)

    single = metrics.boundingRect(rect, flags, "OFERTA")
    multiline = metrics.boundingRect(rect, flags, "OFERTA\nESPECIAL")

    assert not flags & QtCore.Qt.TextSingleLine
    assert not flags & QtCore.Qt.TextWordWrap
    assert multiline.height() > single.height() * 1.5


def test_qt_renderer_draws_linear_gradient_and_outer_shadow(tmp_path):
    report = render_png(_effects_document(), tmp_path / "effects.png", target_width=220)
    assert report.ok

    image = QImage(str(report.output))
    assert not image.isNull()
    left = image.pixelColor(48, 60)
    right = image.pixelColor(152, 60)
    shadow = image.pixelColor(170, 60)
    untouched = image.pixelColor(205, 60)

    assert left.red() > left.blue() * 2
    assert right.blue() > right.red() * 2
    assert shadow.red() < 80 and shadow.green() < 80 and shadow.blue() < 80
    assert untouched.red() > 240 and untouched.green() > 240 and untouched.blue() > 240