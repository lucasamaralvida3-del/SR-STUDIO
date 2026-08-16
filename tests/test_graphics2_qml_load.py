from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
import srstudio.graphics2.qt_host as qt_host


class _Bridge(QObject):
    sceneChanged = Signal()
    statusChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument(name="QML Smoke")))

    @Property(str, notify=sceneChanged)
    def sceneJson(self) -> str:
        return json.dumps(self.router.payload(), ensure_ascii=False, separators=(",", ":"))

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return "QML smoke"

    @Slot(str)
    def selectNode(self, _node_id: str) -> None:
        pass

    @Slot(str, bool, bool)
    def selectNodeAdvanced(self, _node_id: str, _additive: bool, _toggle: bool) -> None:
        pass

    @Slot(float, float)
    def moveSelection(self, _dx: float, _dy: float) -> None:
        pass

    @Slot(float, float, float)
    def moveSelectionAtZoom(self, _dx: float, _dy: float, _zoom: float) -> None:
        pass

    @Slot()
    def undo(self) -> None:
        pass

    @Slot()
    def redo(self) -> None:
        pass

    @Slot(str, str)
    def editText(self, _node_id: str, _text: str) -> None:
        pass

    @Slot(str, result=str)
    def dispatch(self, _payload: str) -> str:
        return '{"ok":true}'


def test_graphics_editor_qml_loads_offscreen_without_component_errors():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    assert engine.rootObjects(), "GraphicsEditor.qml não carregou; há erro de QML ou dependência."
