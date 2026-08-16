from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

from .model import GraphicsDocument
from .operations import GraphicsSession


def qt_quick_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except Exception:
        return False
    return True


def launch_qt_quick_editor(document: GraphicsDocument | None = None) -> int:
    try:
        from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except Exception as exc:
        raise RuntimeError("SR Graphics Engine 2 requer a dependência opcional 'graphics2' (PySide6).") from exc
    session = GraphicsSession(document or GraphicsDocument())

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "SR Graphics Engine 2 pronto"

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(session.document.to_dict(), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        @Slot(str)
        def selectNode(self, node_id: str) -> None:
            session.select(node_id)
            self.sceneChanged.emit()

        @Slot(float, float)
        def moveSelection(self, dx: float, dy: float) -> None:
            session.move_selected(dx, dy)
            self.sceneChanged.emit()

        @Slot()
        def undo(self) -> None:
            if session.undo():
                self.sceneChanged.emit()

        @Slot()
        def redo(self) -> None:
            if session.redo():
                self.sceneChanged.emit()

        @Slot(str, str)
        def editText(self, node_id: str, text: str) -> None:
            session.set_text(node_id, text)
            self.sceneChanged.emit()

        @Slot(str)
        def dispatch(self, payload: str) -> None:
            try:
                command: dict[str, Any] = json.loads(payload)
                name = str(command.get("name") or "")
                if name == "lock":
                    session.lock_selected(bool(command.get("value", True)))
                elif name == "hide":
                    session.hide_selected(bool(command.get("value", True)))
                elif name == "layer":
                    session.layer_selected(str(command.get("mode") or "front"))
                elif name == "rotate":
                    session.rotate_selected(float(command.get("angle") or 0))
                elif name == "opacity":
                    session.set_opacity(float(command.get("value") or 1))
                elif name == "duplicate":
                    session.duplicate_selected()
                elif name == "delete":
                    session.delete_selected()
                elif name == "align":
                    session.align_selected(str(command.get("mode") or "left"))
                elif name == "distribute":
                    session.distribute_selected(str(command.get("axis") or "horizontal"))
                else:
                    raise ValueError(f"Comando desconhecido: {name}")
                self._status = f"Comando executado: {name}"
            except Exception as exc:
                self._status = f"Erro: {exc}"
            self.statusChanged.emit()
            self.sceneChanged.emit()

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("SR Graphics Engine 2")
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(__file__).with_name("qml") / "GraphicsEditor.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    if not engine.rootObjects():
        raise RuntimeError("Falha ao carregar a interface Qt Quick do SR Graphics Engine 2.")
    return int(app.exec())


def main() -> int:
    return launch_qt_quick_editor(GraphicsDocument(name="Novo Projeto SR — Graphics Engine 2"))


if __name__ == "__main__":
    raise SystemExit(main())
