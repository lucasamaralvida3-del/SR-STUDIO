from __future__ import annotations

from pathlib import Path
import json
import sys

from .command_router import GraphicsCommandRouter
from .fonts import register_qt_document_fonts
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
    session = GraphicsSession(document or GraphicsDocument()); router = GraphicsCommandRouter(session)

    class SceneBridge(QObject):
        sceneChanged = Signal(); statusChanged = Signal()
        def __init__(self) -> None:
            super().__init__(); self._status = "SR Graphics Engine 2 pronto"
        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))
        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status
        def _run(self, command: dict) -> None:
            result = router.dispatch(command); self._status = result.message or ("Concluído" if result.ok else "Falha"); self.statusChanged.emit(); self.sceneChanged.emit()
        @Slot(str)
        def selectNode(self, node_id: str) -> None: self._run({"name": "select", "node_id": node_id})
        @Slot(str, bool, bool)
        def selectNodeAdvanced(self, node_id: str, additive: bool, toggle: bool) -> None: self._run({"name": "select", "node_id": node_id, "additive": additive, "toggle": toggle})
        @Slot(float, float)
        def moveSelection(self, dx: float, dy: float) -> None: self._run({"name": "move", "dx": dx, "dy": dy, "snap": True})
        @Slot(float, float, float)
        def moveSelectionAtZoom(self, dx: float, dy: float, zoom: float) -> None: self._run({"name": "move", "dx": dx, "dy": dy, "snap": True, "zoom": zoom})
        @Slot()
        def undo(self) -> None: self._run({"name": "undo"})
        @Slot()
        def redo(self) -> None: self._run({"name": "redo"})
        @Slot(str, str)
        def editText(self, node_id: str, text: str) -> None: self._run({"name": "edit_text", "node_id": node_id, "text": text})
        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            result_raw = router.dispatch_json(payload)
            try: self._status = str(json.loads(result_raw).get("message") or "")
            except Exception: self._status = "Comando processado"
            self.statusChanged.emit(); self.sceneChanged.emit(); return result_raw

    app = QGuiApplication.instance() or QGuiApplication(sys.argv); app.setApplicationName("SR Graphics Engine 2")
    font_report = register_qt_document_fonts(session.document)
    engine = QQmlApplicationEngine(); bridge = SceneBridge()
    if font_report.families:
        bridge._status = "Fontes do projeto carregadas: " + ", ".join(font_report.families)
    elif font_report.warnings:
        bridge._status = font_report.warnings[0]
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(__file__).with_name("qml") / "GraphicsEditor.qml"; engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    if not engine.rootObjects(): raise RuntimeError("Falha ao carregar a interface Qt Quick do SR Graphics Engine 2.")
    return int(app.exec())


def main() -> int: return launch_qt_quick_editor(GraphicsDocument(name="Novo Projeto SR — Graphics Engine 2"))


if __name__ == "__main__": raise SystemExit(main())