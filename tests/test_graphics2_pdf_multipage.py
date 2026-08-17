from __future__ import annotations

import os

import pytest
from pypdf import PdfReader

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.qt_renderer import render_pdf


def _text(value: str, x: float, y: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=value,
        text=value,
        transform=Transform(x=x, y=y, width=500, height=90),
        style={"font_family": "Arial", "font_size": 32, "font_size_unit": "pt", "color": "#111111"},
    )


def test_render_pdf_writes_two_real_pages_with_each_page_geometry(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    document = GraphicsDocument(name="Encarte multipágina")
    first = document.active_page
    first.name = "Ofertas 1"
    first.width = 1080
    first.height = 1350
    first.add_node(_text("PÁGINA 1", 120, 160))

    second = GraphicsPage(name="Ofertas 2", width=1350, height=1080)
    second.add_node(_text("PÁGINA 2", 180, 220))
    document.add_page(second)

    output = tmp_path / "encarte.pdf"
    report = render_pdf(document, output, dpi=300)
    app.processEvents()

    assert report.ok
    assert report.pages == 2
    reader = PdfReader(str(output))
    assert len(reader.pages) == 2

    first_box = reader.pages[0].mediabox
    second_box = reader.pages[1].mediabox
    first_width = float(first_box.width)
    first_height = float(first_box.height)
    second_width = float(second_box.width)
    second_height = float(second_box.height)

    assert first_height > first_width
    assert second_width > second_height
    assert first_width > 0 and first_height > 0
    assert second_width > 0 and second_height > 0
