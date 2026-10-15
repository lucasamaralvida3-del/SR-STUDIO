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


def _spin(app, predicate, timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


def test_editor_shortcuts_respect_text_focus_and_restore_canvas_focus():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QMetaObject, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest

    document = GraphicsDocument(name="Keyboard focus")
    text_node = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Editable",
        text="abcg",
        transform=Transform(x=20, y=30, width=220, height=70),
    )
    document.active_page.add_node(text_node)
    second_page = GraphicsPage(name="Página 2")
    document.pages.append(second_page)
    router = GraphicsCommandRouter(GraphicsSession(document))
    router.dispatch({"name": "select", "node_id": text_node.id})

    class Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.commands: list[str] = []
            self.undo_calls = 0
            self.redo_calls = 0

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return "keyboard-focus-test"

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            command = json.loads(payload)
            self.commands.append(str(command.get("name") or ""))
            if command.get("name") == "select_page":
                page_id = str(command.get("page_id") or "")
                if document.page(page_id) is not None:
                    document.active_page_id = page_id
                self.sceneChanged.emit()
            return json.dumps({"ok": True, "changed": False, "payload": router.payload()})

        @Slot()
        def undo(self) -> None:
            self.undo_calls += 1

        @Slot()
        def redo(self) -> None:
            self.redo_calls += 1

        @Slot(str, str)
        def editText(self, node_id: str, value: str) -> None:
            pass

        @Slot(str, bool, bool)
        def selectNodeAdvanced(self, node_id: str, additive: bool, toggle: bool) -> None:
            router.dispatch({"name": "select", "node_id": node_id, "additive": additive, "toggle": toggle})
            self.sceneChanged.emit()

        @Slot(float, float, float)
        def moveSelectionAtZoom(self, dx: float, dy: float, zoom: float) -> None:
            pass

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    assert _spin(app, lambda: bool(engine.rootObjects())), "GraphicsEditor.qml não carregou."
    root = engine.rootObjects()[0]
    root.show()
    assert _spin(app, lambda: root.isVisible())

    canvas = root.findChild(QObject, "editorCanvasFocusTarget")
    text_field = root.findChild(QObject, "editorGeometryXField")
    text_area = root.findChild(QObject, "editorTextArea")
    assert canvas is not None
    assert text_field is not None
    assert text_area is not None

    def focus(item) -> None:
        assert QMetaObject.invokeMethod(item, "forceActiveFocus")
        assert _spin(app, lambda: bool(item.property("activeFocus")))

    def clear_commands() -> None:
        bridge.commands.clear()

    # 1. Canvas focus + Delete keeps existing canvas behavior.
    focus(canvas)
    clear_commands()
    QTest.keyClick(root, Qt.Key_Delete)
    assert _spin(app, lambda: "delete" in bridge.commands)

    # 2. TextField focus + Delete edits the field and never deletes the node.
    text_field.setProperty("text", "123")
    focus(text_field)
    clear_commands()
    QTest.keyClick(root, Qt.Key_Delete)
    app.processEvents()
    assert "delete" not in bridge.commands

    # 3. TextArea focus + Delete never deletes the selected node.
    text_area.setProperty("text", "abc")
    focus(text_area)
    clear_commands()
    QTest.keyClick(root, Qt.Key_Delete)
    app.processEvents()
    assert "delete" not in bridge.commands

    # 4. G remains text input and does not toggle the grid.
    focus(text_field)
    grid_before = bool(root.property("showGrid"))
    QTest.keyClick(root, Qt.Key_G)
    app.processEvents()
    assert bool(root.property("showGrid")) is grid_before

    # 5. Ctrl+D does not duplicate while a TextField owns focus.
    clear_commands()
    QTest.keyClick(root, Qt.Key_D, Qt.ControlModifier)
    app.processEvents()
    assert "duplicate" not in bridge.commands

    # Audit: group/ungroup shortcuts are suppressed by the same guard.
    QTest.keyClick(root, Qt.Key_G, Qt.ControlModifier)
    QTest.keyClick(root, Qt.Key_G, Qt.ControlModifier | Qt.ShiftModifier)
    app.processEvents()
    assert "group" not in bridge.commands
    assert "ungroup" not in bridge.commands

    # 6. Text editing owns Undo/Redo; canvas bridge receives neither action.
    bridge.undo_calls = 0
    bridge.redo_calls = 0
    QTest.keyClick(root, Qt.Key_Z, Qt.ControlModifier)
    QTest.keyClick(root, Qt.Key_Y, Qt.ControlModifier)
    app.processEvents()
    assert bridge.undo_calls == 0
    assert bridge.redo_calls == 0

    # 7. After leaving the text control, global shortcuts are active again.
    focus(canvas)
    clear_commands()
    QTest.keyClick(root, Qt.Key_D, Qt.ControlModifier)
    assert _spin(app, lambda: "duplicate" in bridge.commands)
    grid_before = bool(root.property("showGrid"))
    QTest.keyClick(root, Qt.Key_G)
    assert _spin(app, lambda: bool(root.property("showGrid")) is not grid_before)

    # 8. A page change cannot leave text-editing focus stuck.
    focus(text_field)
    assert bool(root.property("textEditingActive"))
    document.active_page_id = second_page.id
    bridge.sceneChanged.emit()
    assert _spin(app, lambda: not bool(root.property("textEditingActive")))
    assert bool(canvas.property("activeFocus"))

    # Return to page 1 so the text editor is visible for the final contract.
    document.active_page_id = document.pages[0].id
    bridge.sceneChanged.emit()
    assert _spin(app, lambda: document.active_page_id == document.pages[0].id)

    # 9. Escape closes/cancels text editing and restores canvas focus.
    focus(text_area)
    assert bool(root.property("textEditingActive"))
    QTest.keyClick(root, Qt.Key_Escape)
    assert _spin(app, lambda: not bool(root.property("textEditingActive")))
    assert bool(canvas.property("activeFocus"))

    root.close()
