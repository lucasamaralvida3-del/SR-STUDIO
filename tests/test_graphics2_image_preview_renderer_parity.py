from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6 import QtCore, QtGui
from PySide6.QtGui import QGuiApplication

from srstudio.graphics2.fidelity import FidelityPolicy, compare_images
from srstudio.graphics2.model import AssetRef, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.qt_image_provider import _apply_crop, _compose
from srstudio.graphics2.qt_renderer import render_png


@pytest.fixture(scope="module", autouse=True)
def _qt_application():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def _pattern_source(path) -> None:
    width, height = 160, 120
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (
                (x * 3 + y) % 256,
                (y * 5 + x * 2) % 256,
                ((x + y) * 7) % 256,
            )
    image.save(path)


def _irregular_clip() -> dict:
    return {
        "width": 100,
        "height": 100,
        "paths": [
            {
                "width": 100,
                "height": 100,
                "commands": [
                    {"op": "M", "points": [[12, 8]]},
                    {"op": "L", "points": [[88, 4]]},
                    {"op": "L", "points": [[97, 68]]},
                    {"op": "L", "points": [[62, 96]]},
                    {"op": "L", "points": [[7, 76]]},
                    {"op": "Z"},
                ],
            }
        ],
    }


def _save_preview_equivalent(source, target, *, width: int, height: int, style: dict, clip_path: dict) -> None:
    image = QtGui.QImage(str(source))
    assert not image.isNull()
    image = _apply_crop(image, style.get("crop") or {}, QtCore)
    preview = _compose(image, width, height, style, QtCore, QtGui, clip_path=clip_path)

    # GraphicsEditor.qml aplica mirror/mirrorVertically depois do image provider.
    if style.get("flip_x") or style.get("flip_y"):
        preview = preview.mirrored(bool(style.get("flip_x")), bool(style.get("flip_y")))

    page = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
    page.fill(QtGui.QColor("#FFFFFF"))
    painter = QtGui.QPainter(page)
    assert painter.isActive()
    try:
        painter.drawImage(0, 0, preview)
    finally:
        painter.end()
    assert page.save(str(target), "PNG", 100)


def test_preview_and_production_renderer_match_combined_drawingml_image_contract(tmp_path):
    source = tmp_path / "pattern.png"
    preview_output = tmp_path / "preview.png"
    render_output = tmp_path / "renderer.png"
    _pattern_source(source)

    style = {
        "fit": "cover",
        "crop": {"l": 0.08, "t": 0.12, "r": 0.05, "b": 0.07},
        "fill_rect": {"l": -0.22, "t": -0.08, "r": -0.17, "b": -0.11},
        "flip_x": True,
        "flip_y": True,
    }
    clip_path = _irregular_clip()
    width, height = 120, 90

    _save_preview_equivalent(
        source,
        preview_output,
        width=width,
        height=height,
        style=style,
        clip_path=clip_path,
    )

    document = GraphicsDocument(name="Preview Renderer Image Parity")
    page = document.active_page
    page.width = width
    page.height = height
    page.background = "#FFFFFF"
    asset = AssetRef(kind="image", source=str(source))
    document.assets[asset.id] = asset
    page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            asset_id=asset.id,
            transform=Transform(x=0, y=0, width=width, height=height),
            style=dict(style),
            metadata={"clip_path": clip_path},
        )
    )

    report = render_png(document, render_output, target_width=width)
    assert report.ok

    result = compare_images(
        report.output,
        preview_output,
        name="drawingml-image-preview-renderer-parity",
        policy=FidelityPolicy(
            min_score=0.995,
            min_pixel_pass_ratio=0.98,
            pixel_tolerance=8,
            max_changed_ratio=0.03,
            require_same_size=True,
        ),
        diff_path=tmp_path / "parity-diff.png",
    )

    assert result.passed, result.to_dict()
