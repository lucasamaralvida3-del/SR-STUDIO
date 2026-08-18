from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def _variant_id(value):
    if value is None:
        return None
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value.get("id") if isinstance(value, dict) else None


def test_inspector_fix_diagnostic_states():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    app = QGuiApplication.instance() or QGuiApplication([])

    def run_case(preselected: bool):
        document = GraphicsDocument(name="diagnose")
        image = GraphicsNode(kind=NodeKind.IMAGE, name="Image", transform=Transform(width=100, height=80))
        document.active_page.add_node(image)
        session = GraphicsSession(document)
        router = GraphicsCommandRouter(session)
        if preselected:
            router.dispatch({"name": "select", "node_id": image.id})

        class Bridge(QObject):
            sceneChanged = Signal()
            selectionChanged = Signal()

            @Property(str, notify=sceneChanged)
            def sceneJson(self):
                return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        bridge = Bridge()
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("sceneBridge", bridge)
        qml = Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml"
        engine.load(QUrl.fromLocalFile(str(qml.resolve())))
        for _ in range(30):
            app.processEvents()
        assert engine.rootObjects()
        root = engine.rootObjects()[0]

        def state(label):
            app.processEvents()
            value = {
                "label": label,
                "preselected": preselected,
                "session_selection": sorted(session.selection),
                "anchor_id": session.anchor_id,
                "hasImageSelection": bool(root.property("hasImageSelection")),
                "imageNode": _variant_id(root.property("imageNode")),
                "visible": bool(root.property("visible")),
            }
            print("DIAG_INSPECTOR=" + json.dumps(value, sort_keys=True))
            return value

        initial = state("initial")
        if not preselected:
            router.dispatch({"name": "select", "node_id": image.id})
            bridge.selectionChanged.emit()
            for _ in range(30):
                app.processEvents()
            after_selection = state("after_selection_signal")
        else:
            after_selection = None
        return initial, after_selection

    selected_initial, _ = run_case(True)
    empty_initial, selected_after = run_case(False)

    assert selected_initial["session_selection"]
    assert empty_initial["session_selection"] == []
    assert selected_after and selected_after["session_selection"]
