from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def _variant(value):
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value


def _node_id(value):
    value = _variant(value)
    return value.get("id") if isinstance(value, dict) else None


def _process_events(app, count: int = 4) -> None:
    for _ in range(count):
        app.processEvents()


def test_image_inspector_complete_matrix_matches_real_qquickwindow_host_topology():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    document = GraphicsDocument(name="Image Inspector QQuickWindow certification")
    image_a = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Image A",
        transform=Transform(width=120, height=90),
    )
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Text",
        text="abc",
        transform=Transform(width=120, height=40),
    )
    image_b = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Image B",
        transform=Transform(width=130, height=95),
    )
    for node in (image_a, text, image_b):
        document.active_page.add_node(node)

    page_two = GraphicsPage(name="Page 2")
    page_two_image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Page 2 Image",
        transform=Transform(width=140, height=100),
    )
    page_two.add_node(page_two_image)
    document.pages.append(page_two)

    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    class Bridge(QObject):
        sceneChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self):
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Slot(str, result=str)
        def dispatch(self, raw):
            result = router.dispatch_json(raw)
            self.sceneChanged.emit()
            return result

        def select(self, node_id: str):
            result = router.dispatch({"name": "select", "node_id": node_id})
            assert result.ok
            self.sceneChanged.emit()

        def deselect(self):
            result = router.dispatch({"name": "clear_selection"})
            assert result.ok
            self.sceneChanged.emit()

        def select_page(self, page_id: str):
            result = router.dispatch({"name": "select_page", "page_id": page_id})
            assert result.ok
            self.sceneChanged.emit()

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)

    qml_path = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path.resolve())))
    assert not component.isError(), [error.toString() for error in component.errors()]
    root = component.create(engine.rootContext())
    assert root is not None
    assert isinstance(root, QQuickItem)

    window = QQuickWindow()
    window.resize(1000, 800)
    root.setParentItem(window.contentItem())
    root.setParent(window)
    window.show()
    _process_events(app)

    assert root.parent() is window
    assert root.parentItem() is window.contentItem()
    assert root.window() is window
    assert window.isVisible()

    print(
        "INSPECTOR_TOPOLOGY="
        + json.dumps(
            {
                "parent_is_window": root.parent() is window,
                "parent_item_is_content_item": root.parentItem() is window.contentItem(),
                "root_window_is_window": root.window() is window,
                "window_visible": window.isVisible(),
                "matches_qt_host_attach_contract": True,
            },
            sort_keys=True,
        )
    )

    def snapshot(label: str):
        _process_events(app)
        raw = json.loads(bridge.sceneJson)
        editor = raw.get("editor") or {}
        state = {
            "label": label,
            "selection": sorted(session.selection),
            "anchor": session.anchor_id,
            "scene_selection": editor.get("selection"),
            "scene_anchor": editor.get("anchor_id"),
            "hasImageSelection": bool(root.property("hasImageSelection")),
            "imageNode": _node_id(root.property("imageNode")),
            "visible_property": bool(root.property("visible")),
            "parent_attached": root.parent() is window,
            "parent_item_attached": root.parentItem() is window.contentItem(),
            "window_attached": root.window() is window,
            "window_shown": window.isVisible(),
            "effective_displayability": bool(root.property("visible")) and window.isVisible(),
        }
        print("INSPECTOR_MATRIX=" + json.dumps(state, sort_keys=True))
        return state

    no_selection = snapshot("NO_SELECTION")
    assert no_selection["selection"] == []
    assert no_selection["anchor"] is None
    assert no_selection["hasImageSelection"] is False
    assert no_selection["imageNode"] is None
    assert no_selection["visible_property"] is False

    bridge.select(image_a.id)
    no_image_to_a = snapshot("NO_IMAGE_TO_IMAGE_A")
    assert no_image_to_a["selection"] == [image_a.id]
    assert no_image_to_a["anchor"] == image_a.id
    assert no_image_to_a["scene_selection"] == [image_a.id]
    assert no_image_to_a["scene_anchor"] == image_a.id
    assert no_image_to_a["hasImageSelection"] is True
    assert no_image_to_a["imageNode"] == image_a.id
    assert no_image_to_a["visible_property"] is True
    assert no_image_to_a["effective_displayability"] is True

    bridge.select(text.id)
    image_to_text = snapshot("IMAGE_A_TO_TEXT")
    assert image_to_text["selection"] == [text.id]
    assert image_to_text["anchor"] == text.id
    assert image_to_text["hasImageSelection"] is False
    assert image_to_text["imageNode"] is None
    assert image_to_text["visible_property"] is False

    bridge.select(image_a.id)
    text_to_image = snapshot("TEXT_TO_IMAGE_A")
    assert text_to_image["selection"] == [image_a.id]
    assert text_to_image["anchor"] == image_a.id
    assert text_to_image["hasImageSelection"] is True
    assert text_to_image["imageNode"] == image_a.id
    assert text_to_image["visible_property"] is True

    bridge.select(image_b.id)
    image_a_to_b = snapshot("IMAGE_A_TO_IMAGE_B")
    assert image_a_to_b["selection"] == [image_b.id]
    assert image_a_to_b["anchor"] == image_b.id
    assert image_a_to_b["hasImageSelection"] is True
    assert image_a_to_b["imageNode"] == image_b.id
    assert image_a_to_b["visible_property"] is True
    assert text_to_image["imageNode"] != image_a_to_b["imageNode"]

    bridge.deselect()
    deselect = snapshot("IMAGE_B_TO_DESELECT")
    assert deselect["selection"] == []
    assert deselect["anchor"] is None
    assert deselect["hasImageSelection"] is False
    assert deselect["imageNode"] is None
    assert deselect["visible_property"] is False

    bridge.select(image_b.id)
    before_page_change = snapshot("BEFORE_PAGE_CHANGE")
    assert before_page_change["imageNode"] == image_b.id

    bridge.select_page(page_two.id)
    page_change = snapshot("PAGE_CHANGE")
    assert document.active_page_id == page_two.id
    assert page_change["selection"] == []
    assert page_change["anchor"] is None
    assert page_change["scene_selection"] == []
    assert page_change["scene_anchor"] == ""
    assert page_change["hasImageSelection"] is False
    assert page_change["imageNode"] is None
    assert page_change["visible_property"] is False

    bridge.select(page_two_image.id)
    page_two_image_selected = snapshot("PAGE_CHANGE_THEN_IMAGE")
    assert page_two_image_selected["selection"] == [page_two_image.id]
    assert page_two_image_selected["anchor"] == page_two_image.id
    assert page_two_image_selected["hasImageSelection"] is True
    assert page_two_image_selected["imageNode"] == page_two_image.id
    assert page_two_image_selected["visible_property"] is True

    window.close()


def test_image_inspector_selection_without_scenechanged_remains_diagnostic_only():
    """Documents stale UI when selection changes without the bridge's normal sceneChanged notification."""

    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    document = GraphicsDocument(name="Image Inspector notification diagnostic")
    image = GraphicsNode(kind=NodeKind.IMAGE, name="Image", transform=Transform(width=100, height=80))
    document.active_page.add_node(image)
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    class Bridge(QObject):
        sceneChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self):
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Slot(str, result=str)
        def dispatch(self, raw):
            result = router.dispatch_json(raw)
            self.sceneChanged.emit()
            return result

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml_path = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path.resolve())))
    assert not component.isError(), [error.toString() for error in component.errors()]
    root = component.create(engine.rootContext())
    assert root is not None and isinstance(root, QQuickItem)

    window = QQuickWindow()
    root.setParentItem(window.contentItem())
    root.setParent(window)
    window.show()
    _process_events(app)

    assert bool(root.property("hasImageSelection")) is False
    result = router.dispatch({"name": "select", "node_id": image.id})
    assert result.ok
    _process_events(app)

    diagnostic = {
        "selection": sorted(session.selection),
        "anchor": session.anchor_id,
        "hasImageSelection": bool(root.property("hasImageSelection")),
        "imageNode": _node_id(root.property("imageNode")),
        "visible_property": bool(root.property("visible")),
        "sceneChanged_emitted": False,
        "classification": "diagnostic_only_not_normal_product_flow",
    }
    print("INSPECTOR_SELECTION_ONLY_DIAGNOSTIC=" + json.dumps(diagnostic, sort_keys=True))

    assert diagnostic["selection"] == [image.id]
    assert diagnostic["anchor"] == image.id
    assert diagnostic["hasImageSelection"] is False
    assert diagnostic["imageNode"] is None
    assert diagnostic["visible_property"] is False

    window.close()
