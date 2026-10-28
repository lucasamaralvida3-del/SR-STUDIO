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

    historicalImageBankDone = Signal(bool, str)

    @Slot(result=str)
    def imageBankJson(self) -> str:
        return json.dumps({"images": [{"id": "fixture", "name": "IMAGEM PENDENTE",
                                       "image_path": "", "status": "pending",
                                       "source": "Banco SR", "can_link": False,
                                       "product_id": ""}],
                           "counts": {"pending": 1, "approved": 0, "manual": 0}})

    @Slot(result=str)
    def imageReviewStatesJson(self) -> str:
        return "{}"

    @Slot(str, result=str)
    def imageSuggestionsJson(self, _product_id: str) -> str:
        return "[]"

    @Slot(str)
    def attachProductImagesBatch(self, _payload: str) -> None:
        pass

    @Slot()
    def openImageBankFolder(self) -> None:
        pass

    @Slot(str)
    def importHistoricalReviewZip(self, _source: str) -> None:
        pass

    @Slot(str, str, str)
    def attachProductImage(self, _id: str, _name: str, _source: str) -> None:
        pass



def test_graphics_editor_qml_loads_offscreen_without_component_errors():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    assert engine.rootObjects(), "GraphicsEditor.qml não carregou; há erro de QML ou dependência."
    # Changing to Imagens must instantiate the actual bank gallery rather than
    # reuse the Produtos ListView or raise an unknown bridge-slot exception.
    window = engine.rootObjects()[0]
    window.setProperty("studioSection", 3)
    app.processEvents()
    assert window.property("studioSection") == 3
    inventory = window.property("imageBankInventory")
    assert inventory is not None

