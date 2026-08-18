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


def test_image_inspector_selection_signal_trace():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    document = GraphicsDocument(name="Inspector signal trace")
    image_a = GraphicsNode(kind=NodeKind.IMAGE, name="Image A", transform=Transform(width=100, height=80))
    text = GraphicsNode(kind=NodeKind.TEXT, name="Text", text="abc", transform=Transform(width=100, height=40))
    image_b = GraphicsNode(kind=NodeKind.IMAGE, name="Image B", transform=Transform(width=110, height=90))
    for node in (image_a, text, image_b):
        document.active_page.add_node(node)
    first_page_id = document.active_page.id
    second_page = GraphicsPage(name="Page 2")
    document.pages.append(second_page)

    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    selection_signal_names = ("selectionChanged", "selectedNodeChanged", "selectedIdsChanged", "sessionChanged")
    existing_session_signals = [name for name in selection_signal_names if hasattr(session, name)]
    print("TRACE_SELECTION_SIGNALS_SESSION=" + json.dumps(existing_session_signals))

    class Bridge(QObject):
        sceneChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.scene_signal_count = 0
            self.sceneChanged.connect(self._count_scene_signal)

        @Slot()
        def _count_scene_signal(self) -> None:
            self.scene_signal_count += 1

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            result = router.dispatch_json(payload)
            self.sceneChanged.emit()
            return result

        def select(self, node_id: str) -> dict:
            before = sorted(session.selection)
            print("TRACE_ROUTER_SELECT_CALL=" + node_id)
            result = router.dispatch({"name": "select", "node_id": node_id})
            after = sorted(session.selection)
            signal_before = self.scene_signal_count
            self.sceneChanged.emit()
            return {
                "router_ok": result.ok,
                "selection_before": before,
                "selection_after": after,
                "scene_signal_before": signal_before,
                "scene_signal_after": self.scene_signal_count,
            }

        def deselect(self) -> dict:
            before = sorted(session.selection)
            result = router.dispatch({"name": "clear_selection"})
            after = sorted(session.selection)
            signal_before = self.scene_signal_count
            self.sceneChanged.emit()
            return {
                "router_ok": result.ok,
                "selection_before": before,
                "selection_after": after,
                "scene_signal_before": signal_before,
                "scene_signal_after": self.scene_signal_count,
            }

        def select_page(self, page_id: str) -> dict:
            before = sorted(session.selection)
            result = router.dispatch({"name": "select_page", "page_id": page_id})
            after = sorted(session.selection)
            signal_before = self.scene_signal_count
            self.sceneChanged.emit()
            return {
                "router_ok": result.ok,
                "selection_before": before,
                "selection_after": after,
                "scene_signal_before": signal_before,
                "scene_signal_after": self.scene_signal_count,
            }

    app = QGuiApplication.instance() or QGuiApplication([])
    qml_dir = Path(qt_host.__file__).with_name("qml")
    source_path = qml_dir / "ImageInspector.qml"
    trace_path = qml_dir / "ImageInspectorSignalTrace.qml"
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        "    property bool syncing: false\n",
        "    property bool syncing: false\n"
        "    property int traceRefreshCount: 0\n"
        "    property string traceSelectedId: \"\"\n",
        1,
    )
    source = source.replace(
        "            var selected = selectedImage(parsedScene)\n",
        "            var selected = selectedImage(parsedScene)\n"
        "            traceRefreshCount += 1\n"
        "            traceSelectedId = selected ? String(selected.id || \"\") : \"\"\n",
        1,
    )
    assert "traceRefreshCount += 1" in source
    trace_path.write_text(source, encoding="utf-8")

    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)

    try:
        engine.load(QUrl.fromLocalFile(str(trace_path.resolve())))
        assert _spin(app, lambda: bool(engine.rootObjects()))
        root = engine.rootObjects()[0]

        def snapshot(label: str, command: dict | None = None) -> dict:
            app.processEvents()
            state = {
                "label": label,
                "command": command,
                "session_selection": sorted(session.selection),
                "anchor_id": session.anchor_id,
                "scene_signal_count": bridge.scene_signal_count,
                "refresh_count": int(root.property("traceRefreshCount") or 0),
                "refresh_selected_id": str(root.property("traceSelectedId") or ""),
                "hasImageSelection": bool(root.property("hasImageSelection")),
                "imageNode": _variant_id(root.property("imageNode")),
                "visible": bool(root.property("visible")),
            }
            print("TRACE_TIMELINE=" + json.dumps(state, ensure_ascii=False, sort_keys=True))
            return state

        snapshot("NO_SELECTION")

        cmd = bridge.select(image_a.id)
        a = snapshot("NO_SELECTION_TO_IMAGE_A", cmd)

        cmd = bridge.select(text.id)
        t = snapshot("IMAGE_A_TO_TEXT", cmd)

        cmd = bridge.select(image_a.id)
        a2 = snapshot("TEXT_TO_IMAGE_A", cmd)

        cmd = bridge.select(image_b.id)
        b = snapshot("IMAGE_A_TO_IMAGE_B", cmd)

        cmd = bridge.deselect()
        d = snapshot("IMAGE_B_TO_DESELECT", cmd)

        bridge.select(image_a.id)
        snapshot("RESELECT_IMAGE_A_BEFORE_PAGE_CHANGE")
        cmd = bridge.select_page(second_page.id)
        p2 = snapshot("PAGE_CHANGE_TO_PAGE_2", cmd)

        cmd = bridge.select_page(first_page_id)
        p1 = snapshot("PAGE_CHANGE_BACK_TO_PAGE_1", cmd)

        # Objective invariants for the graph itself; visibility may be the bug under investigation.
        assert a["command"]["selection_after"] == [image_a.id]
        assert a["command"]["scene_signal_after"] == a["command"]["scene_signal_before"] + 1
        assert t["command"]["selection_after"] == [text.id]
        assert a2["command"]["selection_after"] == [image_a.id]
        assert b["command"]["selection_after"] == [image_b.id]
        assert d["command"]["selection_after"] == []
        assert p2["command"]["selection_after"] == []
        assert p1["command"]["selection_after"] == []
        assert existing_session_signals == []
    finally:
        engine.clearComponentCache()
        try:
            trace_path.unlink()
        except OSError:
            pass
