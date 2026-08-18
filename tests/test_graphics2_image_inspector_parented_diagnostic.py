from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def _spin(app, predicate, timeout_s: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


def _variant_id(value):
    if value is None:
        return None
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value.get("id") if isinstance(value, dict) else None


def test_image_inspector_parented_window_visibility_diagnostic():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    document = GraphicsDocument(name="parented diagnostic")
    image = GraphicsNode(kind=NodeKind.IMAGE, name="Image", transform=Transform(width=100, height=80))
    text = GraphicsNode(kind=NodeKind.TEXT, name="Text", text="abc", transform=Transform(width=100, height=40))
    document.active_page.add_node(image)
    document.active_page.add_node(text)
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    class Bridge(QObject):
        sceneChanged = Signal()
        selectionChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self):
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Slot(str, result=str)
        def dispatch(self, payload):
            before = (tuple(sorted(session.selection)), session.anchor_id)
            result = router.dispatch_json(payload)
            after = (tuple(sorted(session.selection)), session.anchor_id)
            if before != after:
                self.selectionChanged.emit()
            self.sceneChanged.emit()
            return result

        def select_scene(self, node_id):
            router.dispatch({"name": "select", "node_id": node_id})
            self.sceneChanged.emit()

        def select_only(self, node_id):
            router.dispatch({"name": "select", "node_id": node_id})
            self.selectionChanged.emit()

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml.resolve())))
    assert not component.isError(), [e.toString() for e in component.errors()]
    root = component.create(engine.rootContext())
    assert root is not None
    assert isinstance(root, QQuickItem)

    window = QQuickWindow()
    window.resize(1000, 800)
    root.setParentItem(window.contentItem())
    root.setParent(window)
    window.show()
    assert _spin(app, lambda: window.isVisible())

    def snap(label):
        app.processEvents()
        state = {
            "label": label,
            "selection": sorted(session.selection),
            "anchor": session.anchor_id,
            "has": bool(root.property("hasImageSelection")),
            "image": _variant_id(root.property("imageNode")),
            "visible": bool(root.property("visible")),
        }
        print("PARENTED_DIAG=" + json.dumps(state, sort_keys=True))
        return state

    s0 = snap("none")
    bridge.select_scene(image.id)
    _spin(app, lambda: True, 0.05)
    s1 = snap("scene_to_image")
    bridge.select_scene(text.id)
    _spin(app, lambda: True, 0.05)
    s2 = snap("scene_to_text")
    bridge.select_only(image.id)
    _spin(app, lambda: True, 0.05)
    s3 = snap("selection_only_to_image")

    assert s0["visible"] is False
    assert s1["selection"] == [image.id]
    assert s2["selection"] == [text.id]
    assert s3["selection"] == [image.id]

    window.close()
