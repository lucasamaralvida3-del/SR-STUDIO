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


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Smart Slot controls from the frozen Graphics2Host runtime.")
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
    editor_rel = "_internal/srstudio/graphics2/qml/GraphicsEditor.qml"
    actions_rel = "_internal/srstudio/graphics2/qml/ProjectActions.qml"
    editor_entry = _manifest_entry(manifest, editor_rel)
    actions_entry = _manifest_entry(manifest, actions_rel)
    editor_hash = _sha256(editor_qml)
    actions_hash = _sha256(actions_qml)
    assert editor_hash == str(editor_entry.get("sha256") or ""), (editor_hash, editor_entry)
    assert actions_hash == str(actions_entry.get("sha256") or ""), (actions_hash, actions_entry)

    editor_text = editor_qml.read_text(encoding="utf-8")
    actions_text = actions_qml.read_text(encoding="utf-8")
    required_editor_terms = [
        "Ajustar Smart Slot",
        "Restaurar Auto",
        "Não-produto",
        "Excluir Slot",
        "adjust_smart_slot",
        "restore_smart_slot_auto",
        "mark_smart_slot_non_product",
        "delete_smart_slot",
        "smartSlotEditMode",
    ]
    for term in required_editor_terms:
        assert term in editor_text, f"frozen GraphicsEditor.qml missing {term!r}"
    for direction in ('"dir":"nw"', '"dir":"n"', '"dir":"ne"', '"dir":"e"', '"dir":"se"', '"dir":"s"', '"dir":"sw"', '"dir":"w"'):
        assert direction in editor_text, f"frozen GraphicsEditor.qml missing resize handle {direction}"

    required_action_terms = [
        "AJUSTAR SMART SLOTS",
        "smartSlotAdjustButton",
        "smartSlotRestoreButton",
        "smartSlotNonProductButton",
        "smartSlotDeleteButton",
    ]
    for term in required_action_terms:
        assert term in actions_text, f"frozen ProjectActions.qml missing {term!r}"

    from PySide6.QtCore import QObject, Property, QMetaObject, QPoint, QPointF, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtTest import QTest

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "Frozen Smart Slot UI evidence"
            self._busy = False
            self.commands: list[dict] = []
            self._scene = {
                "active_page_id": "page-evidence",
                "pages": [
                    {
                        "id": "page-evidence",
                        "name": "Página 1",
                        "slots": {
                            "slot-real-1": {"id": "slot-real-1", "name": "Produto real 1"},
                            "slot-real-2": {"id": "slot-real-2", "name": "Produto real 2"},
                            "slot-real-3": {"id": "slot-real-3", "name": "Produto real 3"},
                            "slot-real-4": {"id": "slot-real-4", "name": "Produto real 4"},
                            "slot-real-5": {"id": "slot-real-5", "name": "Produto real 5"},
                        },
                    }
                ],
            }

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(self._scene, ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return self._busy

        @Slot(str, result=str)
        def dispatch(self, raw: str) -> str:
            try:
                command = json.loads(raw)
            except Exception:
                command = {"raw": raw}
            self.commands.append(command)
            return json.dumps({"ok": True, "changed": False, "message": "evidence"})

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

    app = QGuiApplication.instance() or QGuiApplication(["frozen-smart-slot-ui-evidence"])
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)

    actions_uri = QUrl.fromLocalFile(str(actions_qml)).toString()
    wrapper = f'''import QtQuick\nimport QtQuick.Controls\nimport QtQuick.Window\nApplicationWindow {{\n    id: root\n    objectName: "smartSlotEvidenceWindow"\n    width: 1280\n    height: 180\n    visible: true\n    color: "#EEF3F9"\n    title: "SR Studio G2 — Frozen Smart Slot UI Evidence"\n    property bool smartSlotEditMode: false\n    property bool smartSlotInspectionMode: false\n    property bool smartSlotSnap: true\n    property string selectedSlotId: "slot-real-1"\n    Loader {{ anchors.fill: parent; source: {json.dumps(actions_uri)} }}\n}}\n'''

    component = QQmlComponent(engine)
    component.setData(wrapper.encode("utf-8"), QUrl.fromLocalFile(str(output_dir / "frozen-ui-wrapper.qml")))
    if component.isError():
        raise AssertionError("; ".join(error.toString() for error in component.errors()))
    root = component.create(engine.rootContext())
    if root is None:
        raise AssertionError("Frozen Smart Slot evidence window was not created")

    app.processEvents()
    QTest.qWait(250)
    app.processEvents()

    def child(name: str):
        found = root.findChild(QObject, name)
        assert found is not None, f"QML object not found: {name}"
        return found

    adjust = child("smartSlotAdjustButton")
    assert bool(adjust.property("visible")) is True
    assert bool(adjust.property("enabled")) is True
    assert bool(root.property("smartSlotEditMode")) is False

    clicked_by = "invokeMethod"
    invoked = QMetaObject.invokeMethod(adjust, "click", Qt.ConnectionType.DirectConnection)
    app.processEvents()
    if not invoked or not bool(root.property("smartSlotEditMode")):
        clicked_by = "mouse"
        width = float(adjust.property("width") or 1)
        height = float(adjust.property("height") or 1)
        scene_point = adjust.mapToScene(QPointF(width / 2.0, height / 2.0))
        QTest.mouseClick(
            root,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(round(scene_point.x()), round(scene_point.y())),
        )
        app.processEvents()

    assert bool(root.property("smartSlotEditMode")) is True, "AJUSTAR SMART SLOTS did not activate edit mode"
    assert bool(root.property("smartSlotInspectionMode")) is True, "edit mode did not force slot visibility"
    assert bool(adjust.property("checked")) is True

    restore = child("smartSlotRestoreButton")
    non_product = child("smartSlotNonProductButton")
    delete = child("smartSlotDeleteButton")
    for control in (restore, non_product, delete):
        assert bool(control.property("visible")) is True
        assert bool(control.property("enabled")) is True

    screenshot_path = output_dir / "frozen-smart-slot-ui.png"
    image = root.grabWindow()
    assert not image.isNull(), "QQuickWindow.grabWindow returned a null image"
    assert image.save(str(screenshot_path)), screenshot_path
    assert screenshot_path.is_file() and screenshot_path.stat().st_size > 0

    evidence = {
        "schema": "srstudio/g2-frozen-smart-slot-ui-1",
        "runtime_root": str(runtime_root),
        "executable": executable.name,
        "runtime_manifest": manifest_path.name,
        "graphics_editor_qml_sha256": editor_hash,
        "project_actions_qml_sha256": actions_hash,
        "runtime_manifest_hash_match": True,
        "ui_command_text": str(adjust.property("text") or ""),
        "ui_command_visible": bool(adjust.property("visible")),
        "ui_command_enabled": bool(adjust.property("enabled")),
        "ui_command_clicked_by": clicked_by,
        "smart_slot_edit_mode_after_click": bool(root.property("smartSlotEditMode")),
        "smart_slot_inspection_after_click": bool(root.property("smartSlotInspectionMode")),
        "restore_auto_visible": bool(restore.property("visible")),
        "non_product_visible": bool(non_product.property("visible")),
        "delete_slot_visible": bool(delete.property("visible")),
        "resize_handles_verified": 8,
        "screenshot": screenshot_path.name,
    }
    evidence_path = output_dir / "frozen-smart-slot-ui.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))

    root.close()
    root.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FROZEN SMART SLOT UI: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
