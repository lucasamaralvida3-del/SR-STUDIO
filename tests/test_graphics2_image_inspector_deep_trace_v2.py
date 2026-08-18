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


def _id(obj):
    return None if obj is None else hex(id(obj))


def _variant(value):
    return value.toVariant() if hasattr(value, "toVariant") else value


def _node_id(value):
    value = _variant(value)
    return value.get("id") if isinstance(value, dict) else None


def _events(app):
    for _ in range(5):
        app.processEvents()
        time.sleep(0.002)


def _fixture():
    doc = GraphicsDocument(name="Inspector trace")
    image_a = GraphicsNode(kind=NodeKind.IMAGE, name="Image A", transform=Transform(width=120, height=90))
    text = GraphicsNode(kind=NodeKind.TEXT, name="Text", text="abc", transform=Transform(width=120, height=40))
    image_b = GraphicsNode(kind=NodeKind.IMAGE, name="Image B", transform=Transform(width=130, height=95))
    for node in (image_a, text, image_b):
        doc.active_page.add_node(node)
    page_one = doc.active_page.id
    page_two = GraphicsPage(name="Page 2")
    doc.pages.append(page_two)
    session = GraphicsSession(doc)
    return doc, session, GraphicsCommandRouter(session), image_a, text, image_b, page_one, page_two


def _instrument(tmp_path):
    qml_dir = Path(qt_host.__file__).with_name("qml")
    copied = tmp_path / "qml"
    shutil.copytree(qml_dir, copied)
    qml = copied / "ImageInspector.qml"
    source = qml.read_text(encoding="utf-8")
    marker = "    property bool syncing: false\n"
    source = source.replace(
        marker,
        marker
        + "    property int diagRefreshCount: 0\n"
        + "    property string diagBridgeIdentity: \"\"\n"
        + "    property string diagSelectedId: \"\"\n"
        + "    property string diagSelectedKind: \"\"\n"
        + "    property bool diagCalculatedHas: false\n"
        + "    property var diagCalculatedImage: null\n"
        + "    property bool diagVisibleIntent: bridgeHasImageSelection\n",
        1,
    )
    old = """    function refresh() {\n        syncing = true\n        try {\n            var parsedScene = JSON.parse(sceneBridge.sceneJson)\n            var selected = selectedImage(parsedScene)\n            scene = parsedScene\n            imageNode = selected\n            hasImageSelection = selected !== null && selected !== undefined\n"""
    new = """    function refresh() {\n        diagRefreshCount += 1\n        diagBridgeIdentity = String(sceneBridge.diagIdentity)\n        syncing = true\n        try {\n            var parsedScene = JSON.parse(sceneBridge.sceneJson)\n            var selected = selectedImage(parsedScene)\n            diagSelectedId = selected ? String(selected.id || \"\") : \"\"\n            diagSelectedKind = selected ? String(selected.kind || \"\") : \"\"\n            diagCalculatedHas = selected !== null && selected !== undefined\n            diagCalculatedImage = selected\n            scene = parsedScene\n            imageNode = selected\n            hasImageSelection = selected !== null && selected !== undefined\n"""
    assert old in source
    qml.write_text(source.replace(old, new, 1), encoding="utf-8")
    return qml


def _bridge_class(QObject, Property, Signal, Slot, session, router):
    class Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        @Property(str, constant=True)
        def diagIdentity(self):
            return _id(self)

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

        def select(self, node_id):
            router.dispatch({"name": "select", "node_id": node_id})
            self.sceneChanged.emit()

        def deselect(self):
            router.dispatch({"name": "clear_selection"})
            self.sceneChanged.emit()

        def page(self, page_id):
            router.dispatch({"name": "select_page", "page_id": page_id})
            self.sceneChanged.emit()

    return Bridge


def test_deep_trace_base_refresh_parenthood_and_transitions(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    _, session, router, image_a, text, image_b, _, page_two = _fixture()
    Bridge = _bridge_class(QObject, Property, Signal, Slot, session, router)
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_instrument(tmp_path).resolve())))
    assert not component.isError(), [e.toString() for e in component.errors()]
    root = component.create(engine.rootContext())
    assert root is not None and isinstance(root, QQuickItem)

    root_id, bridge_id, session_id = _id(root), _id(bridge), _id(session)

    def snap(label, phase):
        raw = bridge.sceneJson
        editor = json.loads(raw).get("editor") or {}
        window = root.window()
        state = {
            "label": label,
            "phase": phase,
            "inspector": root_id,
            "refresh_receiver": _id(root),
            "visible_object": _id(root),
            "bridge": bridge_id,
            "qml_bridge": root.property("diagBridgeIdentity"),
            "session": session_id,
            "session_selection": sorted(session.selection),
            "session_anchor": session.anchor_id,
            "scenejson_digest": hashlib.sha256(raw.encode()).hexdigest()[:16],
            "scenejson_selection": editor.get("selection"),
            "scenejson_anchor": editor.get("anchor_id"),
            "scenejson_contains_selection": "selection" in editor and "anchor_id" in editor,
            "refresh_count": int(root.property("diagRefreshCount")),
            "calculated_has": bool(root.property("diagCalculatedHas")),
            "calculated_image": _node_id(root.property("diagCalculatedImage")),
            "calculated_id": root.property("diagSelectedId"),
            "calculated_kind": root.property("diagSelectedKind"),
            "has": bool(root.property("hasImageSelection")),
            "image": _node_id(root.property("imageNode")),
            "visible_property": bool(root.property("visible")),
            "visible_intent": bool(root.property("diagVisibleIntent")),
            "enabled": bool(root.property("enabled")),
            "parent": _id(root.parent()),
            "parentItem": _id(root.parentItem()),
            "window": _id(window),
            "window_visible": bool(window and window.isVisible()),
            "effective_visible_proxy": bool(root.property("visible")) and bool(window and window.isVisible()),
            "component_status": str(component.status()),
        }
        print("INSPECTOR_TRACE=" + json.dumps(state, sort_keys=True))
        return state

    snap("NO_IMAGE", "ORPHAN_INITIAL")
    bridge.select(image_a.id)
    first_immediate = snap("NO_IMAGE_TO_IMAGE", "POST_REFRESH_IMMEDIATE")
    _events(app)
    first_loop = snap("NO_IMAGE_TO_IMAGE", "POST_EVENT_LOOP")

    assert first_immediate["calculated_has"] is True
    assert first_immediate["has"] is True
    assert first_immediate["calculated_image"] == image_a.id
    assert first_immediate["image"] == image_a.id
    assert first_immediate["scenejson_contains_selection"] is True
    assert first_immediate["inspector"] == first_immediate["refresh_receiver"] == first_immediate["visible_object"]
    assert first_immediate["bridge"] == first_immediate["qml_bridge"]
    assert first_loop["has"] is True and first_loop["image"] == image_a.id

    window = QQuickWindow()
    window.resize(1000, 800)
    root.setParentItem(window.contentItem())
    root.setParent(window)
    snap("IMAGE_A", "PARENTED_HIDDEN")
    window.show()
    _events(app)
    shown = snap("IMAGE_A", "PARENTED_SHOWN")

    matrix = []
    def trans(label, fn):
        fn()
        immediate = snap(label, "POST_REFRESH_IMMEDIATE")
        _events(app)
        loop = snap(label, "POST_EVENT_LOOP")
        matrix.append((label, immediate, loop))

    trans("IMAGE_TO_TEXT", lambda: bridge.select(text.id))
    trans("TEXT_TO_IMAGE", lambda: bridge.select(image_a.id))
    trans("IMAGE_A_TO_IMAGE_B", lambda: bridge.select(image_b.id))
    trans("IMAGE_TO_DESELECT", bridge.deselect)
    bridge.select(image_a.id); _events(app)
    trans("PAGE_CHANGE", lambda: bridge.page(page_two.id))

    expected = {
        "IMAGE_TO_TEXT": (False, None),
        "TEXT_TO_IMAGE": (True, image_a.id),
        "IMAGE_A_TO_IMAGE_B": (True, image_b.id),
        "IMAGE_TO_DESELECT": (False, None),
        "PAGE_CHANGE": (False, None),
    }
    for label, immediate, loop in matrix:
        expected_has, expected_image = expected[label]
        assert immediate["calculated_has"] is expected_has
        assert immediate["has"] is expected_has
        assert immediate["image"] == expected_image
        assert loop["has"] is expected_has
        assert loop["image"] == expected_image
        assert immediate["inspector"] == loop["inspector"] == root_id
        assert immediate["bridge"] == loop["bridge"] == bridge_id
        assert immediate["session"] == loop["session"] == session_id

    assert shown["window"] is not None
    window.close()


def test_deep_trace_actual_graphics_editor_host_attachment(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    _, session, router, image_a, _, _, _, _ = _fixture()
    Bridge = _bridge_class(QObject, Property, Signal, Slot, session, router)
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml_dir = Path(qt_host.__file__).with_name("qml")
    engine.load(QUrl.fromLocalFile(str((qml_dir / "GraphicsEditor.qml").resolve())))
    assert engine.rootObjects()
    editor = engine.rootObjects()[0]
    assert isinstance(editor, QQuickWindow)

    component, inspector = qt_host._attach_context_qml_tool(
        engine, editor, _instrument(tmp_path), QQmlComponent=QQmlComponent,
        QQuickItem=QQuickItem, QQuickWindow=QQuickWindow, QUrl=QUrl,
    )
    _events(app)
    before = {
        "editor": _id(editor), "editor_is_qquickwindow": True, "editor_visible": editor.isVisible(),
        "inspector": _id(inspector), "bridge": _id(bridge), "qml_bridge": inspector.property("diagBridgeIdentity"),
        "session": _id(session), "parent": _id(inspector.parent()), "parentItem": _id(inspector.parentItem()),
        "expected_parentItem": _id(editor.contentItem()), "window": _id(inspector.window()),
        "visible_property": bool(inspector.property("visible")), "visible_intent": bool(inspector.property("diagVisibleIntent")),
        "component_status": str(component.status()),
    }
    print("INSPECTOR_HOST_TRACE=" + json.dumps(before, sort_keys=True))
    bridge.select(image_a.id)
    immediate = {
        "phase": "POST_REFRESH_IMMEDIATE", "inspector": _id(inspector), "refresh_receiver": _id(inspector),
        "visible_object": _id(inspector), "bridge": _id(bridge), "qml_bridge": inspector.property("diagBridgeIdentity"),
        "session": _id(session), "selection": sorted(session.selection), "anchor": session.anchor_id,
        "calculated_has": bool(inspector.property("diagCalculatedHas")), "has": bool(inspector.property("hasImageSelection")),
        "calculated_image": _node_id(inspector.property("diagCalculatedImage")), "image": _node_id(inspector.property("imageNode")),
        "visible_property": bool(inspector.property("visible")), "visible_intent": bool(inspector.property("diagVisibleIntent")),
        "window_visible": bool(inspector.window() and inspector.window().isVisible()),
    }
    print("INSPECTOR_HOST_TRACE=" + json.dumps(immediate, sort_keys=True))
    _events(app)
    loop = dict(immediate)
    loop.update(phase="POST_EVENT_LOOP", has=bool(inspector.property("hasImageSelection")),
                image=_node_id(inspector.property("imageNode")), visible_property=bool(inspector.property("visible")),
                visible_intent=bool(inspector.property("diagVisibleIntent")))
    print("INSPECTOR_HOST_TRACE=" + json.dumps(loop, sort_keys=True))

    assert before["parentItem"] == before["expected_parentItem"]
    assert before["window"] == before["editor"]
    assert immediate["inspector"] == immediate["refresh_receiver"] == immediate["visible_object"]
    assert immediate["bridge"] == immediate["qml_bridge"]
    assert immediate["selection"] == [image_a.id]
    assert immediate["calculated_has"] is True and immediate["has"] is True
    assert immediate["image"] == image_a.id
    assert loop["has"] is True and loop["image"] == image_a.id
    editor.close()
