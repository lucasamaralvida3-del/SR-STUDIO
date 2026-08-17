from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("SR_SKIP_QT_TESTS") == "1", reason="Qt tests disabled")
def test_professional_inspector_qml_component_loads_when_qt_available(monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent

    scene = {
        "id": "doc-test",
        "active_page_id": "page-test",
        "pages": [
            {
                "id": "page-test",
                "name": "Página 1",
                "nodes": {},
                "slots": {},
            }
        ],
        "editor": {
            "professional": {
                "inspector": {
                    "target_type": "page",
                    "target_id": "page-test",
                    "title": "Página 1",
                    "sections": ["page"],
                    "properties": ["name"],
                    "slot_id": "",
                },
                "page": {
                    "page_id": "page-test",
                    "index": 0,
                    "count": 1,
                    "can_delete": False,
                    "can_duplicate": True,
                    "can_move_previous": False,
                    "can_move_next": False,
                },
                "usability": {
                    "professional_usable": True,
                    "blockers": 0,
                    "issues": [],
                },
            }
        },
    }

    class Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self):
            return json.dumps(scene, ensure_ascii=False)

        @Property(bool, notify=statusChanged)
        def busy(self):
            return False

        @Slot(str, result=str)
        def dispatch(self, payload):
            return json.dumps(
                {
                    "ok": True,
                    "changed": False,
                    "message": "ok",
                    "payload": scene,
                    "command_payload": {},
                },
                ensure_ascii=False,
            )

    app = QGuiApplication.instance() or QGuiApplication(["g2-professional-qml-test"])
    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(__file__).parents[1] / "src" / "srstudio" / "graphics2" / "qml" / "ProfessionalInspector.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml.resolve())))

    assert not component.isError(), "; ".join(error.toString() for error in component.errors())
    item = component.create(engine.rootContext())
    assert item is not None, "; ".join(error.toString() for error in component.errors())
    app.processEvents()
    item.deleteLater()
    app.processEvents()
