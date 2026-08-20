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


def _process_events_until(app, predicate, *, timeout_s: float = 1.5) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


def _js_field(value, name: str):
    if value is None:
        return None
    prop = getattr(value, "property", None)
    if callable(prop):
        try:
            field = prop(name)
            to_variant = getattr(field, "toVariant", None)
            return to_variant() if callable(to_variant) else field
        except Exception:
            return None
    if isinstance(value, dict):
        return value.get(name)
    return None


def _build_selected_image_router():
    document = GraphicsDocument(name="Image inspector harness A/B")
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=10, y=20, width=200, height=180),
        style={"fit": "cover", "focus_x": 0.4, "focus_y": 0.6, "zoom": 1.2},
    )
    document.active_page.add_node(image)
    router = GraphicsCommandRouter(GraphicsSession(document))
    router.dispatch({"name": "select", "node_id": image.id})
    return router, image


def _bridge_type(QObject, Property, Signal, Slot, router):
    class _Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return False

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            result = router.dispatch_json(payload)
            self.sceneChanged.emit()
            return result

    return _Bridge


def _type_name(value) -> str:
    return type(value).__name__ if value is not None else "None"


def test_base_orphan_exact_original_harness_observation():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem

    router, image = _build_selected_image_router()
    Bridge = _bridge_type(QObject, Property, Signal, Slot, router)
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    assert _process_events_until(app, lambda: bool(engine.rootObjects()))
    root = engine.rootObjects()[0]
    assert isinstance(root, QQuickItem)
    assert _process_events_until(app, lambda: bool(root.property("hasImageSelection")))
    image_node = root.property("imageNode")
    state = {
        "component_created": True,
        "parent": _type_name(root.parent()),
        "parent_item": _type_name(root.parentItem()),
        "qquickwindow": root.window() is not None,
        "window_shown": bool(root.window() and root.window().isVisible()),
        "visible": bool(root.property("visible")),
        "hasImageSelection": bool(root.property("hasImageSelection")),
        "imageNode_id": _js_field(image_node, "id"),
    }
    print("IMAGE_INSPECTOR_BASE_A", json.dumps(state, sort_keys=True, default=str))
    assert state["parent_item"] == "None"
    assert state["qquickwindow"] is False
    assert state["window_shown"] is False
    assert state["hasImageSelection"] is True
    assert state["imageNode_id"] == image.id


def test_base_qquickwindow_hosted_harness_contract():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    router, image = _build_selected_image_router()
    Bridge = _bridge_type(QObject, Property, Signal, Slot, router)
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml.resolve())))
    assert not component.isError(), [error.toString() for error in component.errors()]
    root = component.create(engine.rootContext())
    assert root is not None
    assert isinstance(root, QQuickItem)

    window = QQuickWindow()
    window.resize(640, 720)
    root.setParentItem(window.contentItem())
    root.setParent(window)
    window.show()

    assert _process_events_until(app, lambda: bool(root.property("hasImageSelection")))
    assert _process_events_until(app, lambda: bool(root.property("visible")))
    image_node = root.property("imageNode")
    state = {
        "component_created": True,
        "parent": _type_name(root.parent()),
        "parent_item": _type_name(root.parentItem()),
        "qquickwindow": root.window() is window,
        "window_shown": window.isVisible(),
        "visible": bool(root.property("visible")),
        "hasImageSelection": bool(root.property("hasImageSelection")),
        "imageNode_id": _js_field(image_node, "id"),
    }
    print("IMAGE_INSPECTOR_BASE_B", json.dumps(state, sort_keys=True, default=str))
    assert state["parent"] == "QQuickWindow"
    assert state["parent_item"] in {"QQuickRootItem", "QQuickItem"}
    assert state["qquickwindow"] is True
    assert state["window_shown"] is True
    assert state["hasImageSelection"] is True
    assert state["imageNode_id"] == image.id
    assert state["visible"] is True

    root.setParentItem(None)
    root.setParent(None)
    root.deleteLater()
    window.close()
    window.deleteLater()
    app.processEvents()
