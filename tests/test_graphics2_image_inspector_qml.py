from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform


def _source() -> str:
    return (Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml").read_text(encoding="utf-8")


def test_image_inspector_exposes_crop_focus_zoom_and_flip_controls():
    source = _source()
    assert '"name": "crop"' in source
    assert '"zoom": zoomSlider.value' in source
    assert '"focus_x": focusXSlider.value' in source
    assert '"focus_y": focusYSlider.value' in source
    assert '"flip_x"' in source
    assert '"flip_y"' in source
    assert '"fit": "contain"' in source
    assert '? "cover"' in source
    assert '? "fill"' in source
    assert "property real baseScale" in source
    assert "property bool cropMode" in source


def test_host_loads_image_inspector_as_contextual_qquickitem():
    host = Path(qt_host.__file__).read_text(encoding="utf-8")
    assert 'qml_dir / "ImageInspector.qml"' in host
    assert "QQmlComponent" in host
    assert "setParentItem" in host


def test_image_inspector_qml_loads_offscreen_when_pyside_is_available():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from srstudio.graphics2.command_router import GraphicsCommandRouter
    from srstudio.graphics2.operations import GraphicsSession

    document = GraphicsDocument(name="Image Inspector Smoke")
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=10, y=10, width=220, height=160),
        style={"fit": "contain", "zoom": 1.0, "focus_x": 0.5, "focus_y": 0.5},
    )
    document.active_page.add_node(image)
    session = GraphicsSession(document)
    session.select(image.id)
    router = GraphicsCommandRouter(session)

    class _Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return "Image smoke"

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            return router.dispatch_json(payload)

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    assert engine.rootObjects(), "ImageInspector.qml não carregou; há erro de QML ou dependência."
