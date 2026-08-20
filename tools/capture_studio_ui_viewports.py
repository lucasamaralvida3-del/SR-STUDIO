from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ.setdefault("QSG_RHI_BACKEND", "software")
os.environ.setdefault("QT_SCALE_FACTOR", "1")


def _all_objects(root):
    from PySide6.QtCore import QObject

    return [root, *root.findChildren(QObject)]


def _has_text(root, expected: str) -> bool:
    for obj in _all_objects(root):
        try:
            value = obj.property("text")
        except Exception:
            continue
        if value is not None and str(value) == expected:
            return True
    return False


def _grab_window(root, target: Path) -> tuple[int, int]:
    image = root.grabWindow()
    assert not image.isNull(), f"grabWindow returned null image for {target.name}"
    assert image.save(str(target)), target
    assert target.is_file() and target.stat().st_size > 0
    return image.width(), image.height()


def _build_document():
    from srstudio.graphics2.item_slots import bind_product_to_item_slot, create_item_slot
    from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession

    products = [
        {"id": "prod-1", "display_name": "ALCATRA BOVINA KG", "name": "ALCATRA BOVINA KG", "category": "Carnes", "unit": "KG", "price": 39.99},
        {"id": "prod-2", "display_name": "COCA-COLA 2L", "name": "COCA-COLA 2L", "category": "Bebidas", "unit": "UN", "price": 8.99},
        {"id": "prod-3", "display_name": "ARROZ TIPO 1 5KG", "name": "ARROZ TIPO 1 5KG", "category": "Mercearia", "unit": "UN", "price": 24.90},
        {"id": "prod-4", "display_name": "DETERGENTE 500ML", "name": "DETERGENTE 500ML", "category": "Limpeza", "unit": "UN", "price": 2.49},
        {"id": "prod-5", "display_name": "LEITE INTEGRAL 1L", "name": "LEITE INTEGRAL 1L", "category": "Mercearia", "unit": "UN", "price": 4.79},
    ]
    document = GraphicsDocument(
        name="Studio UI Reconciliation",
        pages=[GraphicsPage(name="Encarte Principal", width=1080, height=1350)],
        metadata={"products": products},
    )
    document.active_page_id = document.pages[0].id
    session = GraphicsSession(document)
    placements = (
        ("simples", 30.0, 280.0, products[0]),
        ("card", 365.0, 280.0, products[1]),
        ("destaque", 700.0, 250.0, products[2]),
    )
    slot_ids = []
    for preset, x, y, product in placements:
        slot = create_item_slot(session, preset, x=x, y=y)
        assert bind_product_to_item_slot(session, slot.id, product)
        slot_ids.append(slot.id)
    session.clear_selection()
    return document, session, products, slot_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture real Qt Studio UI screenshots at supported desktop viewports.")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    from shiboken6 import Shiboken
    from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter, prepare_qml_payload

    runtime_root = args.runtime_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    editor_qml = runtime_root / "_internal" / "srstudio" / "graphics2" / "qml" / "GraphicsEditor.qml"
    assert editor_qml.is_file(), editor_qml

    document, session, products, slot_ids = _build_document()
    router = ItemSlotCommandRouter(session)

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "Studio UI viewport validation"

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            payload = prepare_qml_payload(router.payload())
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return False

        @Slot(str, result=str)
        def dispatch(self, raw: str) -> str:
            result = router.dispatch_json(raw, include_scene_payload=False)
            parsed = json.loads(result)
            self._status = str(parsed.get("message") or "")
            self.statusChanged.emit()
            self.sceneChanged.emit()
            return result

        @Slot(str, bool, bool)
        def selectNodeAdvanced(self, node_id: str, additive: bool, toggle: bool) -> None:
            self.dispatch(json.dumps({"name": "select", "node_id": node_id, "additive": additive, "toggle": toggle}))

        @Slot(float, float, float)
        def moveSelectionAtZoom(self, dx: float, dy: float, zoom_value: float) -> None:
            self.dispatch(json.dumps({"name": "move", "dx": dx, "dy": dy, "zoom": zoom_value}))

        @Slot()
        def undo(self) -> None:
            self.dispatch('{"name":"undo"}')

        @Slot()
        def redo(self) -> None:
            self.dispatch('{"name":"redo"}')

        @Slot(str, str)
        def editText(self, node_id: str, text: str) -> None:
            self.dispatch(json.dumps({"name": "edit_text", "node_id": node_id, "text": text}))

        @Slot()
        def flushAutosave(self) -> None:
            return None

        @Slot(result=bool)
        def recoverLatest(self) -> bool:
            return True

        @Slot(str)
        def saveSceneAs(self, _target: str) -> None:
            return None

        @Slot(str)
        def exportPdf(self, _target: str) -> None:
            return None

        @Slot(str)
        def exportPng(self, _target: str) -> None:
            return None

    app = QGuiApplication.instance() or QGuiApplication(["studio-ui-viewports"])
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(editor_qml.resolve())))
    roots = engine.rootObjects()
    assert roots, "GraphicsEditor.qml did not create a root window"
    root_object = roots[0]
    root_address = int(Shiboken.getCppPointer(root_object)[0])
    root = Shiboken.wrapInstance(root_address, QQuickWindow)
    assert root is not None and Shiboken.isValid(root), "Editor root is not a valid QQuickWindow"

    app.processEvents()
    QTest.qWait(350)
    app.processEvents()

    required_text = ["Studio de Encartes", "Produtos", "Importados da planilha", "Propriedades", "Canvas"]
    missing_text = [text for text in required_text if not _has_text(root, text)]
    assert not missing_text, f"required Studio chrome text missing: {missing_text}"
    assert len(products) == 5
    assert len(slot_ids) == 3

    root.setProperty("zoom", 0.58)
    app.processEvents()
    QTest.qWait(120)
    assert abs(float(root.property("zoom")) - 0.58) < 0.001

    evidence = []
    for width, height in ((1920, 1080), (1600, 900), (1366, 768)):
        root.resize(width, height)
        app.processEvents()
        QTest.qWait(350)
        app.processEvents()
        assert int(root.width()) == width, (root.width(), width)
        assert int(root.height()) == height, (root.height(), height)
        shot = output_dir / f"studio-{width}x{height}.png"
        image_width, image_height = _grab_window(root, shot)
        evidence.append(
            {
                "viewport": f"{width}x{height}",
                "window_width": int(root.width()),
                "window_height": int(root.height()),
                "image_width": image_width,
                "image_height": image_height,
                "screenshot": shot.name,
                "screenshot_bytes": shot.stat().st_size,
                "zoom": float(root.property("zoom")),
                "products": len(products),
                "item_slots": len(slot_ids),
                "compact_ui": bool(root.property("compactUi")),
                "tight_ui": bool(root.property("tightUi")),
            }
        )

    result = {
        "schema": "srstudio/g2-studio-ui-viewports-1",
        "pass": True,
        "required_chrome_text": required_text,
        "missing_chrome_text": missing_text,
        "products_panel_count": len(products),
        "item_slot_presets_visible": ["simples", "card", "destaque"],
        "viewports": evidence,
    }
    (output_dir / "studio-ui-viewports.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    root.close()
    root_object.deleteLater()
    app.processEvents()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
