from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication, QImage

from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.qt_renderer import render_png


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def _document() -> GraphicsDocument:
    document = GraphicsDocument(name="Transparent export")
    page = document.active_page
    page.width = 60
    page.height = 40
    page.background = "#FF0000"
    return document


def test_transparent_png_keeps_page_background_out_of_alpha_channel(tmp_path) -> None:
    report = render_png(_document(), tmp_path / "transparent.png", target_width=60, transparent=True)
    image = QImage(str(report.output))
    pixel = image.pixelColor(20, 20)

    assert pixel.alpha() == 0


def test_opaque_png_still_uses_page_background(tmp_path) -> None:
    report = render_png(_document(), tmp_path / "opaque.png", target_width=60, transparent=False)
    image = QImage(str(report.output))
    pixel = image.pixelColor(20, 20)

    assert pixel.alpha() == 255
    assert (pixel.red(), pixel.green(), pixel.blue()) == (255, 0, 0)
