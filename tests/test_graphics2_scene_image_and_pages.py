from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
import srstudio.graphics2.qt_host as qt_host


def _qml(name: str) -> str:
    return (Path(qt_host.__file__).with_name("qml") / name).read_text(encoding="utf-8")


def test_scene_image_encodes_renderer_fit_zoom_focus_contract():
    source = _qml("SceneImage.qml")
    assert 'fit === "cover" || imageZoom > 1.0001' in source
    assert "Math.max(width / naturalWidth, height / naturalHeight)" in source
    assert "Math.min(width / naturalWidth, height / naturalHeight)" in source
    assert "visualFocusX: flipX ? 1.0 -" in source
    assert "visualFocusY: flipY ? 1.0 -" in source
    assert "(root.width - width) * root.visualFocusX" in source
    assert "(root.height - height) * root.visualFocusY" in source
    assert "mirror: root.flipX" in source
    assert "mirrorVertically: root.flipY" in source
    assert "clip: true" in source


def test_image_inspector_uses_shared_scene_image_component():
    source = _qml("ImageInspector.qml")
    assert "SceneImage {" in source
    assert "imageZoom: zoomSlider.value" in source
    assert "focusX: focusXSlider.value" in source
    assert "focusY: focusYSlider.value" in source


def test_page_inspector_exposes_visual_reorder_controls_and_quality_panel_hosts_it():
    source = _qml("PageInspector.qml")
    quality = _qml("QualityInspector.qml")
    assert '"name": "reorder_page"' in source
    assert '"previous"' in source
    assert '"next"' in source
    assert '"name": "select_page"' in source
    assert "PageInspector {" in quality
    assert "parent: panel.parent" in quality


def test_scene_image_qml_loads_offscreen_when_pyside_is_available():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    qml = Path(qt_host.__file__).with_name("qml") / "SceneImage.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    assert engine.rootObjects(), "SceneImage.qml não carregou; há erro no componente compartilhado."


def _page_router() -> GraphicsCommandRouter:
    document = GraphicsDocument(name="Page Reorder")
    document.pages[0].name = "Página A"
    document.add_page(GraphicsPage(name="Página B"))
    document.add_page(GraphicsPage(name="Página C"))
    document.active_page_id = document.pages[0].id
    return GraphicsCommandRouter(GraphicsSession(document))


def test_page_inspector_qml_loads_offscreen_when_pyside_is_available():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    router = _page_router()

    class _Bridge(QObject):
        sceneChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            result = router.dispatch_json(payload)
            self.sceneChanged.emit()
            return result

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "PageInspector.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    assert engine.rootObjects(), "PageInspector.qml não carregou; há erro no reordenador visual."


def test_reorder_page_moves_active_page_transactionally_and_preserves_identity():
    router = _page_router()
    original_ids = [page.id for page in router.session.document.pages]
    target_id = original_ids[2]

    result = router.dispatch({"name": "reorder_page", "page_id": target_id, "mode": "first"})

    assert result.ok and result.changed
    assert [page.id for page in router.session.document.pages] == [target_id, original_ids[0], original_ids[1]]
    assert router.session.document.active_page_id == target_id
    assert result.payload["index"] == 0

    assert router.session.undo()
    assert [page.id for page in router.session.document.pages] == original_ids

    assert router.session.redo()
    assert [page.id for page in router.session.document.pages] == [target_id, original_ids[0], original_ids[1]]


def test_reorder_page_supports_next_previous_and_explicit_index_without_overflow():
    router = _page_router()
    ids = [page.id for page in router.session.document.pages]

    moved = router.dispatch({"name": "reorder_page", "page_id": ids[0], "mode": "next"})
    assert moved.changed
    assert [page.id for page in router.session.document.pages] == [ids[1], ids[0], ids[2]]

    moved = router.dispatch({"name": "reorder_page", "page_id": ids[0], "target_index": 99})
    assert moved.changed
    assert [page.id for page in router.session.document.pages] == [ids[1], ids[2], ids[0]]

    no_op = router.dispatch({"name": "reorder_page", "page_id": ids[0], "mode": "next"})
    assert no_op.ok and not no_op.changed
    assert [page.id for page in router.session.document.pages] == [ids[1], ids[2], ids[0]]
