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


def _image_node(root):
    value = root.property("imageNode")
    if value is None:
        return None
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value if isinstance(value, dict) else None


def _image_id(root):
    value = _image_node(root)
    return value.get("id") if value else None


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
    assert "position, size, crop" not in source.lower()
    assert "posição, tamanho, crop, rotação e camadas" in source


def test_image_inspector_qml_loads_offscreen_with_selected_image():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    document = GraphicsDocument(name="Image inspector smoke")
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=10, y=20, width=200, height=180),
        style={"fit": "cover", "focus_x": 0.4, "focus_y": 0.6, "zoom": 1.2},
    )
    document.active_page.add_node(image)
    router = GraphicsCommandRouter(GraphicsSession(document))
    router.dispatch({"name": "select", "node_id": image.id})

    class _Bridge(QObject):
        sceneChanged = Signal()
        selectionChanged = Signal()
        statusChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return False

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            before = (tuple(sorted(router.session.selection)), router.session.anchor_id)
            result = router.dispatch_json(payload)
            after = (tuple(sorted(router.session.selection)), router.session.anchor_id)
            if after != before:
                self.selectionChanged.emit()
            self.sceneChanged.emit()
            return result

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))

    assert _process_events_until(app, lambda: bool(engine.rootObjects())), (
        "ImageInspector.qml não carregou no runtime Qt Quick real."
    )
    root = engine.rootObjects()[0]
    assert _process_events_until(app, lambda: root.property("visible") is True), (
        "ImageInspector.qml carregou, mas a seleção de imagem não tornou o painel visível."
    )
    assert _process_events_until(app, lambda: _image_id(root) == image.id)
    assert root.property("height") > 0


def test_image_inspector_tracks_selection_without_scene_mutation_and_scene_refresh():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    document = GraphicsDocument(name="Image inspector transitions")
    image_a = GraphicsNode(kind=NodeKind.IMAGE, name="Imagem A", transform=Transform(width=120, height=90))
    text = GraphicsNode(kind=NodeKind.TEXT, name="Texto", text="abc", transform=Transform(width=140, height=50))
    image_b = GraphicsNode(kind=NodeKind.IMAGE, name="Imagem B", transform=Transform(width=130, height=95))
    for node in (image_a, text, image_b):
        document.active_page.add_node(node)
    page_one = document.active_page.id
    page_two = GraphicsPage(name="Página 2")
    document.pages.append(page_two)
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    class _Bridge(QObject):
        sceneChanged = Signal()
        selectionChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            before = (tuple(sorted(session.selection)), session.anchor_id, document.active_page_id)
            result = router.dispatch_json(payload)
            after = (tuple(sorted(session.selection)), session.anchor_id, document.active_page_id)
            if after != before:
                self.selectionChanged.emit()
            self.sceneChanged.emit()
            return result

        def select_only(self, node_id: str) -> None:
            router.dispatch({"name": "select", "node_id": node_id})
            self.selectionChanged.emit()

        def deselect_only(self) -> None:
            router.dispatch({"name": "clear_selection"})
            self.selectionChanged.emit()

        def page_only(self, page_id: str) -> None:
            router.dispatch({"name": "select_page", "page_id": page_id})
            self.selectionChanged.emit()

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))

    assert _process_events_until(app, lambda: bool(engine.rootObjects()))
    root = engine.rootObjects()[0]

    assert _process_events_until(app, lambda: root.property("visible") is False)

    # Selection mutation only: no sceneChanged emitted in these transitions.
    bridge.select_only(image_a.id)
    assert _process_events_until(app, lambda: root.property("visible") is True)
    assert _process_events_until(app, lambda: _image_id(root) == image_a.id)

    bridge.select_only(text.id)
    assert _process_events_until(app, lambda: root.property("visible") is False)
    assert _process_events_until(app, lambda: _image_id(root) is None)

    bridge.select_only(image_a.id)
    assert _process_events_until(app, lambda: root.property("visible") is True)
    assert _process_events_until(app, lambda: _image_id(root) == image_a.id)

    bridge.select_only(image_b.id)
    assert _process_events_until(app, lambda: root.property("visible") is True)
    assert _process_events_until(app, lambda: _image_id(root) == image_b.id)

    # Scene mutation only while the same image remains selected.
    image_b.name = "Imagem B atualizada"
    bridge.sceneChanged.emit()
    assert _process_events_until(app, lambda: root.property("visible") is True)
    assert _process_events_until(app, lambda: _image_id(root) == image_b.id)
    assert _process_events_until(app, lambda: (_image_node(root) or {}).get("name") == "Imagem B atualizada")

    bridge.deselect_only()
    assert _process_events_until(app, lambda: root.property("visible") is False)
    assert _process_events_until(app, lambda: _image_id(root) is None)

    document.active_page_id = page_one
    bridge.select_only(image_a.id)
    assert _process_events_until(app, lambda: root.property("visible") is True)
    bridge.page_only(page_two.id)
    assert _process_events_until(app, lambda: root.property("visible") is False)
    assert _process_events_until(app, lambda: _image_id(root) is None)


def test_scene_bridge_exposes_selection_specific_signal_without_scene_format_change():
    source = Path(qt_host.__file__).read_text(encoding="utf-8")
    assert "selectionChanged = Signal()" in source
    assert "self.selectionChanged.emit()" in source
    assert "selectionJson" not in source
