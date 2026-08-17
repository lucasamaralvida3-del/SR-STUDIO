from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6 import QtGui
from PySide6.QtGui import QGuiApplication

from srstudio.graphics2.fidelity import FidelityPolicy, compare_images
from srstudio.graphics2.model import AssetRef, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.qt_image_provider import _compose
from srstudio.graphics2.qt_renderer import render_png


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def _pattern(path) -> None:
    width, height = 180, 130
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = ((x * 5 + y) % 256, (y * 7 + x) % 256, (x * 2 + y * 3) % 256)
    image.save(path)


def _preview_with_node_rotation(source, output, *, width: int, height: int, style: dict, rotation: float) -> None:
    image = QtGui.QImage(str(source))
    assert not image.isNull()
    composed = _compose(image, width, height, style, __import__("PySide6.QtCore", fromlist=["QtCore"]), QtGui)

    page = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
    page.fill(QtGui.QColor("#FFFFFF"))
    painter = QtGui.QPainter(page)
    assert painter.isActive()
    try:
        painter.translate(width / 2.0, height / 2.0)
        painter.rotate(rotation)
        painter.translate(-width / 2.0, -height / 2.0)
        painter.drawImage(0, 0, composed)
    finally:
        painter.end()
    assert page.save(str(output), "PNG", 100)


def test_quinta_file_negative_fill_rect_and_minus_180_rotation_match_production_renderer(tmp_path):
    source = tmp_path / "product-pattern.png"
    preview_output = tmp_path / "preview.png"
    render_output = tmp_path / "renderer.png"
    _pattern(source)

    # Contrato observado no PPTX real da Quinta Filé. O Freeform 3 usa rotação
    # -180° e os cards usam outsets negativos desse mesmo tipo para enquadrar a
    # fotografia dentro da caixa do Canva.
    style = {
        "fit": "cover",
        "fill_rect": {"l": -0.30959, "t": 0.0, "r": -0.30437, "b": -0.30482},
        "crop": {},
        "flip_x": False,
        "flip_y": False,
    }
    width, height = 160, 112
    rotation = -180.0

    _preview_with_node_rotation(
        source,
        preview_output,
        width=width,
        height=height,
        style=style,
        rotation=rotation,
    )

    document = GraphicsDocument(name="Quinta File image parity")
    page = document.active_page
    page.width = width
    page.height = height
    page.background = "#FFFFFF"
    asset = AssetRef(kind="image", source=str(source))
    document.assets[asset.id] = asset
    page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            name="Freeform 3",
            asset_id=asset.id,
            transform=Transform(x=0, y=0, width=width, height=height, rotation=rotation),
            style=dict(style),
        )
    )

    report = render_png(document, render_output, target_width=width)
    assert report.ok
    result = compare_images(
        report.output,
        preview_output,
        name="quinta-fillrect-minus180-parity",
        policy=FidelityPolicy(
            min_score=0.995,
            min_pixel_pass_ratio=0.98,
            pixel_tolerance=8,
            max_changed_ratio=0.03,
            require_same_size=True,
        ),
        diff_path=tmp_path / "diff.png",
    )

    assert result.passed, result.to_dict()
