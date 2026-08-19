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


def _type_name(value) -> str:
    return type(value).__name__ if value is not None else "None"


def test_base_orphan_vs_qquickwindow_image_inspector_harness_ab():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    router, image = _build_selected_image_router()

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

    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = _Bridge()
    qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    qml_url = QUrl.fromLocalFile(str(qml.resolve()))

    # A: exact legacy failing harness: top-level ImageInspector loaded directly
    # into QQmlApplicationEngine, with no QQuickWindow/contentItem parent.
    engine_a = QQmlApplicationEngine()
    engine_a.rootContext().setContextProperty("sceneBridge", bridge)
    engine_a.load(qml_url)
    assert _process_events_until(app, lambda: bool(engine_a.rootObjects()))
    orphan = engine_a.rootObjects()[0]
    assert isinstance(orphan, QQuickItem)
    assert _process_events_until(app, lambda: bool(orphan.property("hasImageSelection")))
    orphan_image = orphan.property("imageNode")
    orphan_state = {
        "component_created": orphan is not None,
        "parent": _type_name(orphan.parent()),
        "parent_item": _type_name(orphan.parentItem()),
        "qquickwindow": orphan.window() is not None,
        "window_shown": bool(orphan.window() and orphan.window().isVisible()),
        "visible": bool(orphan.property("visible")),
        "hasImageSelection": bool(orphan.property("hasImageSelection")),
        "imageNode_id": _js_field(orphan_image, "id"),
    }
    print("IMAGE_INSPECTOR_BASE_A", json.dumps(orphan_state, sort_keys=True, default=str))

    # B: same component and bridge, but parented exactly like qt_host.py.
    engine_b = QQmlApplicationEngine()
    engine_b.rootContext().setContextProperty("sceneBridge", bridge)
    component = QQmlComponent(engine_b, qml_url)
    assert not component.isError(), [error.toString() for error in component.errors()]
    hosted = component.create(engine_b.rootContext())
    assert hosted is not None
    assert isinstance(hosted, QQuickItem)
    window = QQuickWindow()
    window.resize(640, 720)
    hosted.setParentItem(window.contentItem())
    hosted.setParent(window)
    window.show()
    assert _process_events_until(app, lambda: bool(hosted.property("hasImageSelection")))
    assert _process_events_until(app, lambda: bool(hosted.property("visible")))
    hosted_image = hosted.property("imageNode")
    hosted_state = {
        "component_created": hosted is not None,
        "parent": _type_name(hosted.parent()),
        "parent_item": _type_name(hosted.parentItem()),
        "qquickwindow": hosted.window() is window,
        "window_shown": window.isVisible(),
        "visible": bool(hosted.property("visible")),
        "hasImageSelection": bool(hosted.property("hasImageSelection")),
        "imageNode_id": _js_field(hosted_image, "id"),
    }
    print("IMAGE_INSPECTOR_BASE_B", json.dumps(hosted_state, sort_keys=True, default=str))

    assert orphan_state["parent_item"] == "None"
    assert orphan_state["qquickwindow"] is False
    assert orphan_state["window_shown"] is False
    assert orphan_state["hasImageSelection"] is True
    assert orphan_state["imageNode_id"] == image.id
    assert orphan_state["visible"] is False

    assert hosted_state["parent"] == "QQuickWindow"
    assert hosted_state["parent_item"] == "QQuickRootItem"
    assert hosted_state["qquickwindow"] is True
    assert hosted_state["window_shown"] is True
    assert hosted_state["hasImageSelection"] is True
    assert hosted_state["imageNode_id"] == image.id
    assert hosted_state["visible"] is True

    hosted.setParentItem(None)
    hosted.setParent(None)
    hosted.deleteLater()
    window.close()
    window.deleteLater()
    app.processEvents()
