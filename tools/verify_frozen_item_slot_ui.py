from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entry(manifest: dict, relative_path: str) -> dict:
    for item in manifest.get("files") or []:
        if isinstance(item, dict) and str(item.get("path") or "").replace("\\", "/") == relative_path:
            return item
    raise AssertionError(f"runtime manifest missing {relative_path}")


def _walk_items(item):
    yield item
    for child in item.childItems():
        yield from _walk_items(child)


def _find_text_object(root, text: str):
    from PySide6.QtCore import QObject

    candidates = [root, *root.findChildren(QObject)]
    for obj in candidates:
        try:
            value = obj.property("text")
        except Exception:
            continue
        if value is not None and str(value) == text:
            return obj
    raise AssertionError(f"QML control not found by text: {text!r}")


def _click(obj) -> str:
    from PySide6.QtCore import QMetaObject, Qt

    if QMetaObject.invokeMethod(obj, "click", Qt.ConnectionType.DirectConnection):
        return "invokeMethod(click)"
    raise AssertionError(f"QML control is not programmatically clickable: {obj}")


def _grab_item(item, path: Path) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    grab = item.grabToImage()
    assert grab is not None, "grabToImage could not start"
    if grab.image().isNull():
        loop = QEventLoop()
        grab.ready.connect(loop.quit)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
    image = grab.image()
    assert not image.isNull(), "grabToImage returned null image"
    assert image.save(str(path)), path
    assert path.is_file() and path.stat().st_size > 0


def _find_sheet(root, page_width: float, page_height: float, zoom: float):
    from PySide6.QtGui import QColor

    expected_w = page_width * zoom
    expected_h = page_height * zoom
    matches = []
    for item in _walk_items(root.contentItem()):
        if abs(float(item.width()) - expected_w) > 2 or abs(float(item.height()) - expected_h) > 2:
            continue
        color = item.property("color")
        if isinstance(color, QColor) and color.alpha() >= 240 and color.red() >= 235 and color.green() >= 235 and color.blue() >= 235:
            matches.append(item)
    assert matches, f"canvas sheet not found at {expected_w}x{expected_h}"
    return matches[0]


def _changed_pixels(before: Path, after: Path) -> tuple[int, tuple[int, int, int, int] | None]:
    from PIL import Image, ImageChops

    with Image.open(before).convert("RGB") as first, Image.open(after).convert("RGB") as second:
        assert first.size == second.size
        diff = ImageChops.difference(first, second)
        bbox = diff.getbbox()
        gray = diff.convert("L")
        changed = sum(1 for value in gray.getdata() if value >= 8)
        return changed, bbox


def _attach_actions(engine, root, actions_qml: Path):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    from PySide6.QtQuick import QQuickItem

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(actions_qml.resolve())))
    if component.isError():
        raise AssertionError("; ".join(error.toString() for error in component.errors()))
    panel = component.create(engine.rootContext())
    if panel is None:
        raise AssertionError("ProjectActions.qml could not be created")
    panel.setParent(root)
    if isinstance(panel, QQuickItem):
        panel.setParentItem(root.contentItem())
    return component, panel


def _visual_node_ids(page, slot) -> dict[str, str]:
    image_backplate = next(
        node.id for node in page.nodes.values()
        if bool(node.metadata.get("item_slot_image_backplate")) and node.parent_id == slot.metadata.get("root_node_id")
    )
    return {
        "image_placeholder": image_backplate,
        "name_placeholder": slot.node_by_role["name"],
        "price_currency": slot.node_by_role["currency"],
        "price_integer": slot.node_by_role["price_reais"],
        "price_decimal": slot.node_by_role["price_cents"],
        "unit_placeholder": slot.node_by_role["unit"],
    }


def _assert_delegate_geometry(sheet, page, node_id: str, zoom: float) -> dict:
    node = page.node(node_id)
    assert node is not None
    target = node.transform
    expected = (target.x * zoom, target.y * zoom, max(1.0, target.width * zoom), max(1.0, target.height * zoom))
    matches = []
    for item in sheet.childItems():
        geometry = (float(item.x()), float(item.y()), float(item.width()), float(item.height()))
        if all(abs(actual - wanted) <= 1.5 for actual, wanted in zip(geometry, expected)) and item.isVisible() and float(item.opacity()) > 0:
            matches.append(item)
    assert matches, f"visible delegate missing for {node.name}: expected={expected}"
    assert target.width > 2 and target.height > 2
    assert 0 <= target.x < page.width and 0 <= target.y < page.height
    assert target.x + target.width <= page.width + 0.01
    assert target.y + target.height <= page.height + 0.01
    return {
        "node_id": node_id,
        "name": node.name,
        "bounds": [target.x, target.y, target.width, target.height],
        "delegate_matches": len(matches),
        "visible": True,
    }


def _run_preset(runtime_root: Path, output_dir: Path, preset_id: str, preset_label: str) -> dict:
    from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest

    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.qt_host import prepare_qml_payload

    qml_root = runtime_root / "_internal" / "srstudio" / "graphics2" / "qml"
    editor_qml = qml_root / "GraphicsEditor.qml"
    actions_qml = qml_root / "ProjectActions.qml"

    document = GraphicsDocument(name=f"Frozen ItemSlot {preset_id}", pages=[GraphicsPage(name="Página 1", width=1080, height=1350)])
    document.active_page_id = document.pages[0].id
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "Frozen ItemSlot visual gate"
            self._busy = False
            self.commands: list[dict] = []
            self.results: list[dict] = []
            self.scene_changed_count = 0
            self.sceneChanged.connect(self._count_scene_change)

        def _count_scene_change(self) -> None:
            self.scene_changed_count += 1

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            payload = prepare_qml_payload(router.payload())
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return self._busy

        @Slot(str, result=str)
        def dispatch(self, raw: str) -> str:
            command = json.loads(raw)
            self.commands.append(command)
            result_raw = router.dispatch_json(raw, include_scene_payload=False)
            result = json.loads(result_raw)
            self.results.append(result)
            self._status = str(result.get("message") or "")
            self.statusChanged.emit()
            self.sceneChanged.emit()
            return result_raw

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

    app = QGuiApplication.instance() or QGuiApplication(["frozen-item-slot-ui-gate"])
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(editor_qml.resolve())))
    roots = engine.rootObjects()
    assert roots, "Frozen GraphicsEditor.qml did not create a root window"
    root = roots[0]
    actions_component, panel = _attach_actions(engine, root, actions_qml)
    keep_alive = (actions_component, panel)
    assert keep_alive

    app.processEvents()
    QTest.qWait(250)
    app.processEvents()

    zoom = float(root.property("zoom"))
    sheet = _find_sheet(root, session.page.width, session.page.height, zoom)
    before_path = output_dir / f"{preset_id}-before.png"
    after_path = output_dir / f"{preset_id}-after.png"
    _grab_item(sheet, before_path)
    before_child_count = len(sheet.childItems())
    before_scene = bridge.sceneJson
    before_slots = len(session.page.slots)
    before_nodes = len(session.page.nodes)

    add_button = _find_text_object(root, "+ SLOT DE ITEM")
    add_clicked_by = _click(add_button)
    app.processEvents()
    QTest.qWait(80)
    app.processEvents()

    preset_control = _find_text_object(root, preset_label)
    preset_clicked_by = _click(preset_control)
    app.processEvents()
    QTest.qWait(250)
    app.processEvents()

    add_commands = [command for command in bridge.commands if command.get("name") == "add_item_slot"]
    assert add_commands, "QML preset selection did not send add_item_slot"
    assert add_commands[-1].get("preset_id") == preset_id
    assert bridge.results and bridge.results[-1].get("ok") is True
    assert len(session.page.slots) == before_slots + 1
    assert len(session.page.nodes) > before_nodes
    assert bridge.scene_changed_count >= 1
    assert bridge.sceneJson != before_scene

    slot = next(iter(session.page.slots.values()))
    assert slot.metadata.get("manual_item_slot") is True
    assert slot.metadata.get("preset_id") == preset_id
    assert slot.metadata.get("state") == "empty"
    assert slot.product_id == ""
    root_node = session.page.node(str(slot.metadata.get("root_node_id") or ""))
    assert root_node is not None
    assert root_node.visible is True
    assert root_node.transform.width > 2 and root_node.transform.height > 2
    assert 0 <= root_node.transform.x < session.page.width
    assert 0 <= root_node.transform.y < session.page.height
    assert root_node.transform.x + root_node.transform.width <= session.page.width + 0.01
    assert root_node.transform.y + root_node.transform.height <= session.page.height + 0.01

    visual_ids = _visual_node_ids(session.page, slot)
    delegate_evidence = {
        role: _assert_delegate_geometry(sheet, session.page, node_id, zoom)
        for role, node_id in visual_ids.items()
    }

    # Remove selection so the visual proof cannot pass solely because of the blue
    # selection outline. The empty placeholders themselves must remain visible.
    bridge.dispatch('{"name":"clear_selection"}')
    app.processEvents()
    QTest.qWait(120)
    app.processEvents()
    _grab_item(sheet, after_path)
    after_child_count = len(sheet.childItems())
    changed_pixels, diff_bbox = _changed_pixels(before_path, after_path)
    assert after_child_count > before_child_count, (before_child_count, after_child_count)
    assert changed_pixels >= 500, f"canvas changed only {changed_pixels} pixels; empty slot is not visibly represented"
    assert diff_bbox is not None

    evidence = {
        "preset_id": preset_id,
        "preset_label": preset_label,
        "add_clicked_by": add_clicked_by,
        "preset_clicked_by": preset_clicked_by,
        "commands": bridge.commands,
        "slot_count_before": before_slots,
        "slot_count_after": len(session.page.slots),
        "node_count_before": before_nodes,
        "node_count_after": len(session.page.nodes),
        "scene_changed_count": bridge.scene_changed_count,
        "page_model_updated": bridge.sceneJson != before_scene,
        "root_bounds": [root_node.transform.x, root_node.transform.y, root_node.transform.width, root_node.transform.height],
        "root_visible": root_node.visible,
        "empty_state": slot.metadata.get("state"),
        "product_id": slot.product_id,
        "delegate_evidence": delegate_evidence,
        "sheet_child_count_before": before_child_count,
        "sheet_child_count_after": after_child_count,
        "changed_pixels_after_clear_selection": changed_pixels,
        "diff_bbox": list(diff_bbox) if diff_bbox else None,
        "before_screenshot": before_path.name,
        "after_screenshot": after_path.name,
    }

    root.close()
    root.deleteLater()
    app.processEvents()
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen Windows gate for + SLOT DE ITEM -> visible canvas component.")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = runtime_root / "graphics2-host-runtime.json"
    qml_root = runtime_root / "_internal" / "srstudio" / "graphics2" / "qml"
    editor_qml = qml_root / "GraphicsEditor.qml"
    actions_qml = qml_root / "ProjectActions.qml"
    executable = runtime_root / "SRGraphicsEngine2Host.exe"
    for required in (manifest_path, editor_qml, actions_qml, executable):
        assert required.is_file(), required

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {}
    for relative, path in (
        ("_internal/srstudio/graphics2/qml/GraphicsEditor.qml", editor_qml),
        ("_internal/srstudio/graphics2/qml/ProjectActions.qml", actions_qml),
    ):
        entry = _manifest_entry(manifest, relative)
        actual = _sha256(path)
        assert actual == str(entry.get("sha256") or ""), (relative, actual, entry)
        hashes[relative] = actual

    action_text = actions_qml.read_text(encoding="utf-8")
    assert "+ SLOT DE ITEM" in action_text
    assert "add_item_slot" in action_text
    assert "SIMPLES" not in action_text or "item_slot_presets" in action_text

    presets = [
        ("simples", "SIMPLES"),
        ("destaque", "DESTAQUE"),
        ("card", "CARD PREÇO SOBREPOSTO"),
    ]
    results = []
    for preset_id, label in presets:
        results.append(_run_preset(runtime_root, output_dir, preset_id, label))

    evidence = {
        "schema": "srstudio/g2-frozen-item-slot-visible-1",
        "runtime_root": str(runtime_root),
        "executable": executable.name,
        "runtime_manifest_hash_match": True,
        "qml_sha256": hashes,
        "presets": results,
        "all_visible": all(item["changed_pixels_after_clear_selection"] >= 500 for item in results),
    }
    evidence_path = output_dir / "frozen-item-slot-visible.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FROZEN ITEM SLOT UI: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
