from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def _spin(app, *, iterations: int = 4) -> None:
    for _ in range(iterations):
        app.processEvents()
        time.sleep(0.002)


def _variant(value):
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value


def _node_id(value):
    value = _variant(value)
    return value.get("id") if isinstance(value, dict) else None


def _obj_id(value) -> str | None:
    return None if value is None else hex(id(value))


def _instrumented_qml(tmp_path: Path) -> Path:
    qml_dir = Path(qt_host.__file__).with_name("qml")
    copy_dir = tmp_path / "qml"
    shutil.copytree(qml_dir, copy_dir)
    target = copy_dir / "ImageInspector.qml"
    source = target.read_text(encoding="utf-8")

    declaration = "    property bool syncing: false\n"
    assert declaration in source
    source = source.replace(
        declaration,
        declaration
        + "    property int diagRefreshCount: 0\n"
        + "    property string diagBridgeIdentity: \"\"\n"
        + "    property string diagSceneJsonDigest: \"\"\n"
        + "    property string diagExpectedSelectedId: \"\"\n"
        + "    property string diagExpectedSelectedKind: \"\"\n"
        + "    property bool diagCalculatedHasImageSelection: false\n"
        + "    property var diagCalculatedImageNode: null\n"
        + "    property bool diagVisibleBindingValue: bridgeHasImageSelection\n",
        1,
    )

    old_refresh = """    function refresh() {\n        syncing = true\n        try {\n            var parsedScene = JSON.parse(sceneBridge.sceneJson)\n            var selected = selectedImage(parsedScene)\n            scene = parsedScene\n            imageNode = selected\n            hasImageSelection = selected !== null && selected !== undefined\n"""
    new_refresh = """    function refresh() {\n        diagRefreshCount += 1\n        diagBridgeIdentity = String(sceneBridge.diagIdentity)\n        syncing = true\n        try {\n            var rawSceneJson = sceneBridge.sceneJson\n            diagSceneJsonDigest = String(sceneBridge.diagSceneJsonDigest)\n            var parsedScene = JSON.parse(rawSceneJson)\n            var selected = selectedImage(parsedScene)\n            diagExpectedSelectedId = selected ? String(selected.id || \"\") : \"\"\n            diagExpectedSelectedKind = selected ? String(selected.kind || \"\") : \"\"\n            diagCalculatedImageNode = selected\n            diagCalculatedHasImageSelection = selected !== null && selected !== undefined\n            scene = parsedScene\n            imageNode = selected\n            hasImageSelection = selected !== null && selected !== undefined\n"""
    assert old_refresh in source
    source = source.replace(old_refresh, new_refresh, 1)
    target.write_text(source, encoding="utf-8")
    return target


def _build_fixture():
    document = GraphicsDocument(name="Inspector deep trace")
    image_a = GraphicsNode(kind=NodeKind.IMAGE, name="Image A", transform=Transform(width=120, height=90))
    text = GraphicsNode(kind=NodeKind.TEXT, name="Text", text="abc", transform=Transform(width=120, height=40))
    image_b = GraphicsNode(kind=NodeKind.IMAGE, name="Image B", transform=Transform(width=130, height=95))
    for node in (image_a, text, image_b):
        document.active_page.add_node(node)
    page_one = document.active_page.id
    page_two = GraphicsPage(name="Page 2")
    document.pages.append(page_two)
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    return document, session, router, image_a, text, image_b, page_one, page_two


def test_base_image_inspector_refresh_object_identity_parenthood_and_transition_matrix(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    document, session, router, image_a, text, image_b, page_one, page_two = _build_fixture()

    class Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self):
            super().__init__()
            self._scene_json_calls = 0
            self._last_digest = ""

        @Property(str, constant=True)
        def diagIdentity(self):
            return _obj_id(self)

        @Property(str, notify=sceneChanged)
        def diagSceneJsonDigest(self):
            return self._last_digest

        @Property(str, notify=sceneChanged)
        def sceneJson(self):
            self._scene_json_calls += 1
            raw = json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))
            self._last_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
            return raw

        @Property(str, notify=statusChanged)
        def status(self):
            return "trace"

        @Property(bool, notify=statusChanged)
        def busy(self):
            return False

        @Slot(str, result=str)
        def dispatch(self, raw):
            result = router.dispatch_json(raw)
            self.sceneChanged.emit()
            return result

        def select(self, node_id: str):
            router.dispatch({"name": "select", "node_id": node_id})
            self.sceneChanged.emit()

        def deselect(self):
            router.dispatch({"name": "clear_selection"})
            self.sceneChanged.emit()

        def select_page(self, page_id: str):
            router.dispatch({"name": "select_page", "page_id": page_id})
            self.sceneChanged.emit()

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = _instrumented_qml(tmp_path)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml.resolve())))
    assert not component.isError(), [error.toString() for error in component.errors()]
    root = component.create(engine.rootContext())
    assert root is not None and isinstance(root, QQuickItem)

    inspector_id = _obj_id(root)
    bridge_id = _obj_id(bridge)
    session_id = _obj_id(session)

    def snap(label: str, phase: str):
        raw = bridge.sceneJson
        parsed = json.loads(raw)
        editor = parsed.get("editor") or {}
        parent_item = root.parentItem()
        window = root.window()
        state = {
            "label": label,
            "phase": phase,
            "inspector_object_id": inspector_id,
            "refresh_receiver_object_id": _obj_id(root),
            "visible_property_object_id": _obj_id(root),
            "scene_bridge_object_id": bridge_id,
            "qml_scene_bridge_identity": root.property("diagBridgeIdentity"),
            "session_object_id": session_id,
            "session_selection": sorted(session.selection),
            "session_anchor_id": session.anchor_id,
            "scene_json_calls": bridge._scene_json_calls,
            "scene_json_digest": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
            "scene_json_editor_selection": editor.get("selection"),
            "scene_json_editor_anchor_id": editor.get("anchor_id"),
            "scene_json_contains_selection": "selection" in editor and "anchor_id" in editor,
            "refresh_count": int(root.property("diagRefreshCount")),
            "refresh_calculated_has": bool(root.property("diagCalculatedHasImageSelection")),
            "refresh_calculated_image": _node_id(root.property("diagCalculatedImageNode")),
            "refresh_expected_selected_id": root.property("diagExpectedSelectedId"),
            "refresh_expected_selected_kind": root.property("diagExpectedSelectedKind"),
            "post_has": bool(root.property("hasImageSelection")),
            "post_image": _node_id(root.property("imageNode")),
            "visible_property": bool(root.property("visible")),
            "visible_binding_value": bool(root.property("diagVisibleBindingValue")),
            "enabled": bool(root.property("enabled")),
            "parent_object_id": _obj_id(root.parent()),
            "parent_item_object_id": _obj_id(parent_item),
            "window_object_id": _obj_id(window),
            "window_visible": bool(window and window.isVisible()),
            "effective_visible_proxy": bool(root.property("visible")) and bool(window and window.isVisible()),
            "component_status": int(component.status()),
        }
        print("INSPECTOR_DEEP_TRACE=" + json.dumps(state, sort_keys=True))
        return state

    orphan_initial = snap("NO_IMAGE", "ORPHAN_INITIAL")
    bridge.select(image_a.id)
    no_image_to_image_immediate = snap("NO_IMAGE_TO_IMAGE", "POST_REFRESH_IMMEDIATE")
    _spin(app)
    no_image_to_image_loop = snap("NO_IMAGE_TO_IMAGE", "POST_EVENT_LOOP")

    assert no_image_to_image_immediate["refresh_calculated_has"] is True
    assert no_image_to_image_immediate["post_has"] is True
    assert no_image_to_image_immediate["refresh_calculated_image"] == image_a.id
    assert no_image_to_image_immediate["post_image"] == image_a.id
    assert no_image_to_image_immediate["scene_json_contains_selection"] is True
    assert no_image_to_image_immediate["inspector_object_id"] == no_image_to_image_immediate["refresh_receiver_object_id"]
    assert no_image_to_image_immediate["inspector_object_id"] == no_image_to_image_immediate["visible_property_object_id"]
    assert no_image_to_image_immediate["scene_bridge_object_id"] == no_image_to_image_immediate["qml_scene_bridge_identity"]

    window = QQuickWindow()
    window.resize(1000, 800)
    root.setParentItem(window.contentItem())
    root.setParent(window)
    parented_hidden = snap("IMAGE_A", "PARENTED_WINDOW_HIDDEN")
    window.show()
    _spin(app)
    parented_shown = snap("IMAGE_A", "PARENTED_WINDOW_SHOWN")

    transitions = []

    def transition(label: str, action):
        action()
        immediate = snap(label, "POST_REFRESH_IMMEDIATE")
        _spin(app)
        after_loop = snap(label, "POST_EVENT_LOOP")
        transitions.append((label, immediate, after_loop))

    transition("IMAGE_TO_TEXT", lambda: bridge.select(text.id))
    transition("TEXT_TO_IMAGE", lambda: bridge.select(image_a.id))
    transition("IMAGE_A_TO_IMAGE_B", lambda: bridge.select(image_b.id))
    transition("IMAGE_TO_DESELECT", bridge.deselect)
    bridge.select(image_a.id)
    _spin(app)
    transition("PAGE_CHANGE", lambda: bridge.select_page(page_two.id))

    assert orphan_initial["parent_item_object_id"] is None
    assert no_image_to_image_immediate["visible_binding_value"] is True
    assert no_image_to_image_loop["post_has"] is True
    assert parented_shown["window_object_id"] is not None
    assert parented_shown["visible_binding_value"] is True

    expected = {
        "IMAGE_TO_TEXT": (False, None),
        "TEXT_TO_IMAGE": (True, image_a.id),
        "IMAGE_A_TO_IMAGE_B": (True, image_b.id),
        "IMAGE_TO_DESELECT": (False, None),
        "PAGE_CHANGE": (False, None),
    }
    for label, immediate, after_loop in transitions:
        expected_has, expected_image = expected[label]
        assert immediate["refresh_calculated_has"] is expected_has
        assert immediate["post_has"] is expected_has
        assert immediate["post_image"] == expected_image
        assert after_loop["post_has"] is expected_has
        assert after_loop["post_image"] == expected_image
        assert immediate["inspector_object_id"] == after_loop["inspector_object_id"] == inspector_id
        assert immediate["scene_bridge_object_id"] == after_loop["scene_bridge_object_id"] == bridge_id
        assert immediate["session_object_id"] == after_loop["session_object_id"] == session_id

    window.close()


def test_actual_graphics_editor_host_attachment_identity(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    _, session, router, image_a, _, _, _, _ = _build_fixture()

    class Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        @Property(str, constant=True)
        def diagIdentity(self):
            return _obj_id(self)

        @Property(str, notify=sceneChanged)
        def diagSceneJsonDigest(self):
            raw = json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        @Property(str, notify=sceneChanged)
        def sceneJson(self):
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self):
            return "trace"

        @Property(bool, notify=statusChanged)
        def busy(self):
            return False

        @Slot(str, result=str)
        def dispatch(self, raw):
            result = router.dispatch_json(raw)
            self.sceneChanged.emit()
            return result

        def select(self, node_id: str):
            router.dispatch({"name": "select", "node_id": node_id})
            self.sceneChanged.emit()

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml_dir = Path(qt_host.__file__).with_name("qml")
    engine.load(QUrl.fromLocalFile(str((qml_dir / "GraphicsEditor.qml").resolve())))
    assert engine.rootObjects(), "GraphicsEditor.qml did not load"
    editor = engine.rootObjects()[0]
    assert isinstance(editor, QQuickWindow), type(editor)

    instrumented = _instrumented_qml(tmp_path)
    component, inspector = qt_host._attach_context_qml_tool(
        engine,
        editor,
        instrumented,
        QQmlComponent=QQmlComponent,
        QQuickItem=QQuickItem,
        QQuickWindow=QQuickWindow,
        QUrl=QUrl,
    )
    assert isinstance(inspector, QQuickItem)
    _spin(app)

    before = {
        "editor_object_id": _obj_id(editor),
        "editor_is_qquickwindow": isinstance(editor, QQuickWindow),
        "editor_visible": editor.isVisible(),
        "inspector_object_id": _obj_id(inspector),
        "scene_bridge_object_id": _obj_id(bridge),
        "qml_scene_bridge_identity": inspector.property("diagBridgeIdentity"),
        "session_object_id": _obj_id(session),
        "parent_object_id": _obj_id(inspector.parent()),
        "parent_item_object_id": _obj_id(inspector.parentItem()),
        "expected_parent_item_object_id": _obj_id(editor.contentItem()),
        "window_object_id": _obj_id(inspector.window()),
        "visible_property": bool(inspector.property("visible")),
        "visible_binding_value": bool(inspector.property("diagVisibleBindingValue")),
        "component_status": int(component.status()),
    }
    print("INSPECTOR_HOST_TRACE=" + json.dumps(before, sort_keys=True))

    bridge.select(image_a.id)
    immediate = {
        "phase": "POST_REFRESH_IMMEDIATE",
        "inspector_object_id": _obj_id(inspector),
        "refresh_receiver_object_id": _obj_id(inspector),
        "visible_property_object_id": _obj_id(inspector),
        "scene_bridge_object_id": _obj_id(bridge),
        "qml_scene_bridge_identity": inspector.property("diagBridgeIdentity"),
        "session_object_id": _obj_id(session),
        "selection": sorted(session.selection),
        "anchor": session.anchor_id,
        "refresh_calculated_has": bool(inspector.property("diagCalculatedHasImageSelection")),
        "has": bool(inspector.property("hasImageSelection")),
        "refresh_calculated_image": _node_id(inspector.property("diagCalculatedImageNode")),
        "image": _node_id(inspector.property("imageNode")),
        "visible_property": bool(inspector.property("visible")),
        "visible_binding_value": bool(inspector.property("diagVisibleBindingValue")),
        "window_visible": bool(inspector.window() and inspector.window().isVisible()),
    }
    print("INSPECTOR_HOST_TRACE=" + json.dumps(immediate, sort_keys=True))
    _spin(app)
    after_loop = dict(immediate)
    after_loop.update(
        phase="POST_EVENT_LOOP",
        refresh_calculated_has=bool(inspector.property("diagCalculatedHasImageSelection")),
        has=bool(inspector.property("hasImageSelection")),
        refresh_calculated_image=_node_id(inspector.property("diagCalculatedImageNode")),
        image=_node_id(inspector.property("imageNode")),
        visible_property=bool(inspector.property("visible")),
        visible_binding_value=bool(inspector.property("diagVisibleBindingValue")),
        window_visible=bool(inspector.window() and inspector.window().isVisible()),
    )
    print("INSPECTOR_HOST_TRACE=" + json.dumps(after_loop, sort_keys=True))

    assert before["parent_item_object_id"] == before["expected_parent_item_object_id"]
    assert before["window_object_id"] == before["editor_object_id"]
    assert immediate["inspector_object_id"] == immediate["refresh_receiver_object_id"] == immediate["visible_property_object_id"]
    assert immediate["scene_bridge_object_id"] == immediate["qml_scene_bridge_identity"]
    assert immediate["selection"] == [image_a.id]
    assert immediate["refresh_calculated_has"] is True
    assert immediate["has"] is True
    assert immediate["image"] == image_a.id
    assert after_loop["has"] is True
    assert after_loop["image"] == image_a.id

    editor.close()
