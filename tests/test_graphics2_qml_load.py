from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtCore import QMetaObject
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


def test_slot_selection_survives_its_own_root_but_date_clears_product_inspector():
    from srstudio.graphics2.item_slots import create_item_slot
    from srstudio.graphics2.model import GraphicsNode, NodeKind, Transform
    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = _Bridge()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    window = engine.rootObjects()[0]
    slot = create_item_slot(bridge.router.session, "individual-beta44")
    bridge.sceneChanged.emit()
    app.processEvents()
    window.setProperty("selectedSlotId", slot.id)
    QMetaObject.invokeMethod(window, "syncInspector")
    assert window.property("selectedSlotId") == slot.id
    date = GraphicsNode(kind=NodeKind.TEXT, name="Data da promoção",
                        transform=Transform(x=10, y=10, width=100, height=20),
                        metadata={"campaign_date": True})
    bridge.router.session.page.add_node(date)
    bridge.router.dispatch({"name": "select", "node_id": date.id})
    bridge.sceneChanged.emit()
    app.processEvents()
    QMetaObject.invokeMethod(window, "syncInspector")
    assert window.property("selectedSlotId") == ""
    assert window.property("inspectorProduct") is None

