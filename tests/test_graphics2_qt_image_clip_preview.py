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


def test_preview_cache_signature_changes_when_fill_rect_changes():
    source = "C:/BancoSR/produto.png"
    node = {
        "asset_id": "asset-1",
        "transform": {"width": 300, "height": 200},
        "style": {
            "fit": "cover",
            "fill_rect": {"l": -0.20, "t": 0, "r": -0.10, "b": 0},
        },
        "metadata": {},
    }
    before = _preview_signature(node, source)
    node["style"]["fill_rect"]["l"] = -0.30
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

    assert result.pixelColor(10, 10).alpha() > 240
    assert result.pixelColor(90, 90).alpha() == 0


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
    assert result.pixelColor(90, 10).alpha() > 240
    assert result.pixelColor(10, 90).alpha() == 0


def test_qt_preview_uses_drawingml_fill_rect_before_generic_cover_policy():
    pytest.importorskip("PySide6")
    from PySide6 import QtCore, QtGui

    source = QtGui.QImage(100, 100, QtGui.QImage.Format_ARGB32_Premultiplied)
    source.fill(QtGui.QColor("#00FF00"))
    painter = QtGui.QPainter(source)
    painter.fillRect(QtCore.QRect(0, 0, 25, 100), QtGui.QColor("#FF0000"))
    painter.fillRect(QtCore.QRect(75, 0, 25, 100), QtGui.QColor("#0000FF"))
    painter.end()

    result = _compose(
        source,
        100,
        100,
        {
            "fit": "cover",
            "fill_rect": {"l": -0.5, "t": 0, "r": -0.5, "b": 0},
            "flip_x": False,
            "flip_y": False,
        },
        QtCore,
        QtGui,
    )

    # O BLIP ocupa -50..150. A área visível 0..100 enxerga somente o miolo
    # verde da fotografia; um cover genérico mostraria vermelho/azul nas bordas.
    left = result.pixelColor(5, 50)
    right = result.pixelColor(95, 50)
    assert left.green() > 220 and left.red() < 40 and left.blue() < 40
    assert right.green() > 220 and right.red() < 40 and right.blue() < 40
