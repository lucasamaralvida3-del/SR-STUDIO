from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtGui import QGuiApplication

from srstudio.graphics2.model import AssetRef, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.qt_renderer import render_png


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def _stripe_source(path) -> None:
    image = Image.new("RGB", (100, 100), "#00FF00")
    pixels = image.load()
    for y in range(100):
        for x in range(25):
            pixels[x, y] = (255, 0, 0)
        for x in range(75, 100):
            pixels[x, y] = (0, 0, 255)
    image.save(path)


def test_production_renderer_stretches_blip_to_fill_rect_and_clips_to_shape(tmp_path):
    source = tmp_path / "stripe.png"
    _stripe_source(source)

    document = GraphicsDocument(name="DrawingML fillRect")
    page = document.active_page
    page.width = 100
    page.height = 100
    page.background = "#FFFFFF"
    asset = AssetRef(kind="image", source=str(source))
    document.assets[asset.id] = asset
    page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            asset_id=asset.id,
            transform=Transform(x=0, y=0, width=100, height=100),
            style={
                "fit": "cover",
                "fill_rect": {"l": -0.5, "t": 0, "r": -0.5, "b": 0},
                "crop": {},
                "flip_x": False,
                "flip_y": False,
            },
        )
    )

    report = render_png(document, tmp_path / "fill.png", target_width=100)

    assert report.ok
    with Image.open(report.output).convert("RGB") as rendered:
        left = rendered.getpixel((5, 50))
        right = rendered.getpixel((95, 50))
    assert left[1] > 220 and left[0] < 40 and left[2] < 40
    assert right[1] > 220 and right[0] < 40 and right[2] < 40
