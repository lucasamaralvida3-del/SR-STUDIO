from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication, QImage

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.qt_renderer import _effective_opacity, render_png


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def _grouped_document() -> tuple[GraphicsDocument, GraphicsNode]:
    document = GraphicsDocument(name="Group opacity")
    page = document.active_page
    page.width = 100
    page.height = 100
    page.background = "#FFFFFF"

    outer = GraphicsNode(
        id="outer-group",
        kind=NodeKind.GROUP,
        name="Outer",
        opacity=0.5,
        transform=Transform(x=0, y=0, width=100, height=100),
    )
    inner = GraphicsNode(
        id="inner-group",
        kind=NodeKind.GROUP,
        name="Inner",
        opacity=0.5,
        transform=Transform(x=0, y=0, width=100, height=100),
    )
    child = GraphicsNode(
        id="child-rect",
        kind=NodeKind.RECT,
        name="Child",
        opacity=1.0,
        transform=Transform(x=10, y=10, width=80, height=80),
        style={"fill": "#000000"},
    )
    page.add_node(outer)
    page.add_node(inner, parent_id=outer.id)
    page.add_node(child, parent_id=inner.id)
    return document, child


def test_renderer_multiplies_nested_group_opacity() -> None:
    document, child = _grouped_document()

    assert _effective_opacity(document.active_page, child) == pytest.approx(0.25)


def test_group_opacity_changes_exported_pixels(tmp_path) -> None:
    document, _ = _grouped_document()

    report = render_png(document, tmp_path / "group-opacity.png", target_width=100)
    image = QImage(str(report.output))
    center = image.pixelColor(50, 50)

    # Preto a 25% sobre fundo branco produz aproximadamente RGB 191.
    assert 189 <= center.red() <= 193
    assert center.red() == center.green() == center.blue()
