from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def _source() -> str:
    return (Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml").read_text(encoding="utf-8")


def _process_events_until(app, predicate, *, timeout_s: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


def _qml_field(value, name: str):
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


def test_image_inspector_exposes_replace_file_dialog_without_removing_crop_controls():
    source = _source()
    assert "QtQuick.Dialogs" in source
    assert "Substituir imagem…" in source
    assert '"name": "replace_image"' in source
    assert "FileDialog.OpenFile" in source
    assert "*.png *.jpg *.jpeg *.jfif *.webp" in source
    assert '"name": "crop"' in source
    assert "crop_reset" in source
    assert "focus_x" in source
    assert "focus_y" in source
    assert '"flip_x"' in source
    assert '"flip_y"' in source
    assert "position, size, crop" not in source.lower()  # mensagem continua em português
    assert "posição, tamanho, crop, rotação e camadas" in source


def test_image_inspector_qml_loads_offscreen_with_selected_image():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    page_a = GraphicsPage(name="Página A")
    image_a = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto A",
        transform=Transform(x=10, y=20, width=200, height=180),
        style={"fit": "cover", "focus_x": 0.4, "focus_y": 0.6, "zoom": 1.2},
    )
    image_b = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto B",
        transform=Transform(x=230, y=20, width=200, height=180),
        style={"fit": "contain", "focus_x": 0.5, "focus_y": 0.5, "zoom": 1.0},
    )
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Texto",
        text="Produto",
        transform=Transform(x=10, y=230, width=200, height=60),
    )
    page_a.add_node(image_a)
    page_a.add_node(image_b)
    page_a.add_node(text)

    page_b = GraphicsPage(name="Página B")
    image_page_b = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto Página B",
        transform=Transform(x=30, y=40, width=180, height=160),
        style={"fit": "cover"},
    )
    page_b.add_node(image_page_b)

    document = GraphicsDocument(
        name="Image inspector hosted smoke",
        pages=[page_a, page_b],
        active_page_id=page_a.id,
    )
    router = GraphicsCommandRouter(GraphicsSession(document))

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
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
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

    assert root.parent() is window
    assert root.parentItem() is window.contentItem()
    assert root.window() is window
    assert _process_events_until(app, lambda: window.isVisible())

    def image_node_id():
        return _qml_field(root.property("imageNode"), "id")

    def assert_state(*, has_image: bool, visible: bool, node_id: str | None):
        assert _process_events_until(
            app,
            lambda: bool(root.property("hasImageSelection")) is has_image
            and bool(root.property("visible")) is visible
            and image_node_id() == node_id,
        ), {
            "hasImageSelection": root.property("hasImageSelection"),
            "visible": root.property("visible"),
            "imageNode": image_node_id(),
            "expected": {"hasImageSelection": has_image, "visible": visible, "imageNode": node_id},
        }

    def dispatch(command: dict):
        response = json.loads(bridge.dispatch(json.dumps(command, ensure_ascii=False)))
        assert response["ok"] is True, response
        app.processEvents()
        return response

    # NO IMAGE
    assert_state(has_image=False, visible=False, node_id=None)

    # NO IMAGE -> IMAGE A
    dispatch({"name": "select", "node_id": image_a.id})
    assert_state(has_image=True, visible=True, node_id=image_a.id)

    # IMAGE A -> TEXT
    dispatch({"name": "select", "node_id": text.id})
    assert_state(has_image=False, visible=False, node_id=None)

    # TEXT -> IMAGE A
    dispatch({"name": "select", "node_id": image_a.id})
    assert_state(has_image=True, visible=True, node_id=image_a.id)

    # IMAGE A -> IMAGE B / IMAGE NODE A -> B UPDATE
    dispatch({"name": "select", "node_id": image_b.id})
    assert_state(has_image=True, visible=True, node_id=image_b.id)

    # DESELECT
    dispatch({"name": "clear_selection"})
    assert_state(has_image=False, visible=False, node_id=None)

    # PAGE CHANGE clears selection and therefore hides inspector.
    dispatch({"name": "select", "node_id": image_a.id})
    assert_state(has_image=True, visible=True, node_id=image_a.id)
    dispatch({"name": "select_page", "page_id": page_b.id})
    assert_state(has_image=False, visible=False, node_id=None)

    # Selection still updates correctly after page change.
    dispatch({"name": "select", "node_id": image_page_b.id})
    assert_state(has_image=True, visible=True, node_id=image_page_b.id)

    assert root.property("height") > 0

    root.setParentItem(None)
    root.setParent(None)
    root.deleteLater()
    window.close()
    window.deleteLater()
    app.processEvents()
