from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Use a real Qt Quick window, but default to the offscreen platform so the CI
# runner's small virtual desktop does not clamp the requested capture size.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")
os.environ.setdefault("QT_SCALE_FACTOR", "1")


def _all_objects(root):
    from PySide6.QtCore import QObject

    return [root, *root.findChildren(QObject)]


def _walk_items(item):
    yield item
    for child in item.childItems():
        yield from _walk_items(child)


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


def _find_sheet(root, page_width: float, page_height: float, zoom: float):
    from PySide6.QtGui import QColor

    expected_w = page_width * zoom
    expected_h = page_height * zoom
    matches = []
    for item in _walk_items(root.contentItem()):
        if abs(float(item.width()) - expected_w) > 2 or abs(float(item.height()) - expected_h) > 2:
            continue
        color = item.property("color")
        if (
            isinstance(color, QColor)
            and color.alpha() >= 240
            and color.red() >= 235
            and color.green() >= 235
            and color.blue() >= 235
        ):
            matches.append(item)
    assert matches, f"canvas sheet not found at {expected_w}x{expected_h}"
    return matches[0]


def _variant_map(value):
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return value if isinstance(value, dict) else None


def _find_product_item(root, product_id: str):
    for item in _walk_items(root.contentItem()):
        try:
            data = _variant_map(item.property("productData"))
        except Exception:
            continue
        if data and str(data.get("id") or "") == product_id:
            return item
    raise AssertionError(f"ProductListItem not found for {product_id}")


def _build_document():
    from srstudio.graphics2.item_slots import bind_product_to_item_slot, create_item_slot
    from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession

    products = [
        {"id": "prod-1", "display_name": "ALCATRA BOVINA KG", "name": "ALCATRA BOVINA KG", "category": "Carnes", "unit": "KG", "price": 39.99, "image": "fixture://prod-1.png"},
        {"id": "prod-2", "display_name": "COCA-COLA 2L", "name": "COCA-COLA 2L", "category": "Bebidas", "unit": "UN", "price": 8.99, "image": "fixture://prod-2.png"},
        {"id": "prod-3", "display_name": "ARROZ TIPO 1 5KG", "name": "ARROZ TIPO 1 5KG", "category": "Mercearia", "unit": "UN", "price": 24.90, "image": "fixture://prod-3.png"},
        {"id": "prod-4", "display_name": "DETERGENTE 500ML", "name": "DETERGENTE 500ML", "category": "Limpeza", "unit": "UN", "price": 2.49, "image": "fixture://prod-4.png"},
        {"id": "prod-5", "display_name": "LEITE INTEGRAL 1L", "name": "LEITE INTEGRAL 1L", "category": "Mercearia", "unit": "UN", "price": 4.79, "image": "fixture://prod-5.png"},
    ]
    document = GraphicsDocument(
        name="Studio UI Reconciliation",
        pages=[GraphicsPage(name="Encarte Principal", width=1080, height=1350)],
    )
    document.metadata["products"] = products
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
    session.selection.clear()
    session.anchor_id = None
    return document, session, products, slot_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture real Qt Studio UI screenshots at supported desktop viewports.")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    from shiboken6 import Shiboken
    from PySide6.QtCore import QObject, QPointF, Property, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter, prepare_qml_payload
    from srstudio.graphics2.model import BindingRole

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
            self.commands: list[dict] = []

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
            command = json.loads(raw)
            self.commands.append(command)
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
    QTest.qWait(160)
    assert abs(float(root.property("zoom")) - 0.58) < 0.001

    sheet = _find_sheet(root, session.page.width, session.page.height, float(root.property("zoom")))
    target_slot = session.page.slots[slot_ids[0]]
    target_root = session.page.node(str(target_slot.metadata.get("root_node_id") or ""))
    assert target_root is not None
    drag_product = products[4]
    source_item = _find_product_item(root, drag_product["id"])
    target_sheet_point = QPointF(
        (target_root.transform.x + target_root.transform.width / 2.0) * float(root.property("zoom")),
        (target_root.transform.y + target_root.transform.height / 2.0) * float(root.property("zoom")),
    )
    target_source_point = source_item.mapFromItem(sheet, target_sheet_point)

    begin_drag = getattr(root, "beginProductDrag", None)
    update_drag = getattr(root, "updateProductDrag", None)
    finish_drag = getattr(root, "finishProductDrag", None)
    assert callable(begin_drag) and callable(update_drag) and callable(finish_drag), "QML product drag functions are not callable"
    begin_drag(source_item, float(source_item.width()) / 2.0, float(source_item.height()) / 2.0, drag_product)
    update_drag(source_item, target_source_point.x(), target_source_point.y(), drag_product)
    app.processEvents()
    hit_slot_id = str(root.property("dragHoverSlotId") or "")
    assert hit_slot_id == target_slot.id, (hit_slot_id, target_slot.id)
    assert bool(root.property("productDragActive")) is True
    finish_drag(source_item, target_source_point.x(), target_source_point.y(), drag_product)
    app.processEvents()
    QTest.qWait(180)
    app.processEvents()

    assert target_slot.product_id == drag_product["id"], (target_slot.product_id, drag_product["id"])
    assert any(command.get("name") == "drop_product" for command in bridge.commands)
    assert bool(root.property("productDragActive")) is False

    name_node = session.page.node(target_slot.node_by_role[BindingRole.NAME.value])
    integer_node = session.page.node(target_slot.node_by_role[BindingRole.PRICE_REAIS.value])
    decimal_node = session.page.node(target_slot.node_by_role[BindingRole.PRICE_CENTS.value])
    unit_node = session.page.node(target_slot.node_by_role[BindingRole.UNIT.value])
    image_node = session.page.node(target_slot.node_by_role[BindingRole.IMAGE.value])
    assert name_node is not None and name_node.text == "LEITE INTEGRAL 1L"
    assert integer_node is not None and integer_node.text == "4"
    assert decimal_node is not None and decimal_node.text == ",79"
    assert unit_node is not None and unit_node.text == "/UN"
    assert image_node is not None and image_node.metadata.get("bound_image_source") == drag_product["image"]
    assert image_node.metadata.get("placeholder") is False

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
        assert image_width == width and image_height == height, (shot.name, image_width, image_height)
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
        "schema": "srstudio/g2-studio-ui-viewports-3",
        "pass": True,
        "qt_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "grab_method": "QQuickWindow.grabWindow",
        "required_chrome_text": required_text,
        "missing_chrome_text": missing_text,
        "products_panel_count": len(products),
        "item_slot_presets_visible": ["simples", "card", "destaque"],
        "zoom_runtime": {"set_to": 0.58, "read_back": float(root.property("zoom")), "pass": True},
        "product_drag_runtime": {
            "pass": True,
            "product_id": drag_product["id"],
            "product_name": drag_product["name"],
            "target_slot_id": target_slot.id,
            "hit_test_slot_id": hit_slot_id,
            "highlight_active_before_drop": hit_slot_id == target_slot.id,
            "drop_product_dispatched": any(command.get("name") == "drop_product" for command in bridge.commands),
            "slot_product_id_after_drop": target_slot.product_id,
            "name_applied": name_node.text,
            "price_integer_applied": integer_node.text,
            "price_decimal_applied": decimal_node.text,
            "unit_applied": unit_node.text,
            "image_applied": image_node.metadata.get("bound_image_source"),
            "image_placeholder_after_drop": image_node.metadata.get("placeholder"),
        },
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
