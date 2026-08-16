from __future__ import annotations

import pytest

from srstudio.graphics2.qt_image_provider import _compose, _preview_signature


def _triangle_clip() -> dict:
    return {
        "width": 100,
        "height": 100,
        "paths": [
            {
                "width": 100,
                "height": 100,
                "commands": [
                    {"op": "M", "points": [[0, 0]]},
                    {"op": "L", "points": [[100, 0]]},
                    {"op": "L", "points": [[0, 100]]},
                    {"op": "Z"},
                ],
            }
        ],
    }


def test_preview_cache_signature_changes_when_clip_geometry_changes():
    source = "C:/BancoSR/produto.png"
    node = {
        "asset_id": "asset-1",
        "transform": {"width": 300, "height": 200},
        "style": {"fit": "cover", "zoom": 1.0, "focus_x": 0.5, "focus_y": 0.5},
        "metadata": {"clip_path": _triangle_clip()},
    }
    before = _preview_signature(node, source)
    node["metadata"]["clip_path"]["paths"][0]["commands"][1]["points"][0][0] = 80
    after = _preview_signature(node, source)

    assert before != after


def test_qt_preview_applies_custom_clip_path_before_returning_image():
    pytest.importorskip("PySide6")
    from PySide6 import QtCore, QtGui

    source = QtGui.QImage(100, 100, QtGui.QImage.Format_ARGB32_Premultiplied)
    source.fill(QtGui.QColor("#FF0000"))

    result = _compose(
        source,
        100,
        100,
        {"fit": "fill", "flip_x": False, "flip_y": False},
        QtCore,
        QtGui,
        clip_path=_triangle_clip(),
    )

    assert QtGui.QColor(result.pixel(10, 10)).alpha() > 240
    assert QtGui.QColor(result.pixel(90, 90)).alpha() == 0


def test_qt_preview_pre_mirrors_clip_when_qml_will_mirror_image():
    pytest.importorskip("PySide6")
    from PySide6 import QtCore, QtGui

    source = QtGui.QImage(100, 100, QtGui.QImage.Format_ARGB32_Premultiplied)
    source.fill(QtGui.QColor("#00FF00"))

    result = _compose(
        source,
        100,
        100,
        {"fit": "fill", "flip_x": True, "flip_y": False},
        QtCore,
        QtGui,
        clip_path=_triangle_clip(),
    )

    # O provider entrega a máscara pré-espelhada. O Image QML fará o segundo
    # espelhamento e o contorno final voltará à orientação original do template.
    assert QtGui.QColor(result.pixel(90, 10)).alpha() > 240
    assert QtGui.QColor(result.pixel(10, 90)).alpha() == 0
