from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

os.environ.setdefault("QSG_RHI_BACKEND", "software")


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_hash(manifest: dict, relative_path: str) -> str:
    for entry in manifest.get("files") or []:
        if str(entry.get("path") or "").replace("\\", "/") == relative_path:
            return str(entry.get("sha256") or "")
    raise AssertionError(f"runtime manifest missing {relative_path}")


def _percentile(samples: list[float], percentile: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _summary(samples: list[float]) -> dict[str, float | int]:
    return {
        "median_ms": round(float(median(samples)), 4) if samples else 0.0,
        "p95_ms": round(_percentile(samples, 0.95), 4),
        "max_ms": round(max(samples), 4) if samples else 0.0,
        "samples": len(samples),
    }


def _legacy_contract(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {"available": False}
    text = path.read_text(encoding="utf-8")
    node_start = text.find("                            Repeater {\n                                model: page ? nodes()")
    slot_start = text.find("\n                            Repeater {\n                                model: slots()", node_start)
    node_block = text[node_start:slot_start] if node_start >= 0 and slot_start > node_start else ""
    selection_start = text.find("\n                            Item {\n                                id: selectionOverlay", slot_start)
    wheel_start = text.find("\n                    WheelHandler {", selection_start)
    selection_block = text[selection_start:wheel_start] if selection_start >= 0 and wheel_start > selection_start else ""
    return {
        "available": bool(node_block and selection_block),
        "generic_group_drag_target": "drag.target: parent" in node_block,
        "move_press_select_dispatch": "sceneBridge.selectNodeAdvanced" in node_block,
        "move_position_preview_handler": "onPositionChanged:" in node_block,
        "move_release_backend_commit": "sceneBridge.moveSelectionAtZoom" in node_block,
        "resize_position_preview_handler": "onPositionChanged:" in selection_block,
        "resize_release_backend_commit": '"name": "resize_handle"' in selection_block,
        "item_slot_local_preview_present": "itemSlotPreviewActive" in text,
    }


def _assert_role_relatives_preserved(before: dict, after: dict) -> float:
    drift = 0.0
    before_roles = before.get("internal_roles") or {}
    after_roles = after.get("internal_roles") or {}
    assert set(before_roles) == set(after_roles)
    for role in before_roles:
        left = list(before_roles[role].get("relative") or [])
        right = list(after_roles[role].get("relative") or [])
        assert len(left) == len(right) == 4
        for a, b in zip(left, right):
            drift = max(drift, abs(float(a) - float(b)))
    return drift


def _round_bounds(node) -> list[float]:
    return [
        round(float(node.transform.x), 6),
        round(float(node.transform.y), 6),
        round(float(node.transform.width), 6),
        round(float(node.transform.height), 6),
    ]


def _run_preset(qml_path: Path, preset_id: str) -> dict:
    from shiboken6 import Shiboken
    from PySide6.QtCore import QObject, Property, QPoint, QPointF, Qt, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow
    from PySide6.QtTest import QTest

    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.item_slots import item_slot_snapshot
    from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.package import load_package, save_package
    from srstudio.graphics2.qt_host import prepare_qml_payload

    document = GraphicsDocument(
        name=f"ItemSlot interaction {preset_id}",
        pages=[GraphicsPage(name="Página 1", width=1080, height=1350)],
    )
    document.active_page_id = document.pages[0].id
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)
    add = router.dispatch({"name": "add_item_slot", "preset_id": preset_id})
    assert add.ok and add.payload
    slot_id = str(add.payload["slot_id"])
    slot = session.page.slots[slot_id]
    root_id = str(slot.metadata.get("root_node_id") or "")
    root_node = session.page.node(root_id)
    assert root_node is not None
    before_snapshot = item_slot_snapshot(session.page, slot)
    before_root_bounds = _round_bounds(root_node)
    child_id = str(slot.node_by_role.get("name") or slot.node_by_role.get("image") or "")
    child_node = session.page.node(child_id)
    assert child_node is not None
    initial_child_bounds = _round_bounds(child_node)

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "ItemSlot interaction benchmark"
            self.commands: list[dict] = []
            self.dispatch_samples: list[float] = []

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
            started = perf_counter_ns()
            command = json.loads(raw)
            self.commands.append(command)
            result_raw = router.dispatch_json(raw, include_scene_payload=False)
            result = json.loads(result_raw)
            self._status = str(result.get("message") or "")
            self.statusChanged.emit()
            self.sceneChanged.emit()
            self.dispatch_samples.append((perf_counter_ns() - started) / 1_000_000.0)
            return result_raw

        @Slot(str, bool, bool)
        def selectNodeAdvanced(self, node_id: str, additive: bool, toggle: bool) -> None:
            self.dispatch(json.dumps({
                "name": "select",
                "node_id": node_id,
                "additive": additive,
                "toggle": toggle,
                "semantic": True,
                "semantic_scope": "auto",
            }))

        @Slot(float, float, float)
        def moveSelectionAtZoom(self, dx: float, dy: float, zoom_value: float) -> None:
            self.dispatch(json.dumps({"name": "move", "dx": dx, "dy": dy, "zoom": zoom_value}))

        @Slot()
        def undo(self) -> None:
            return None

        @Slot()
        def redo(self) -> None:
            return None

        @Slot(str, str)
        def editText(self, _node_id: str, _text: str) -> None:
            return None

    app = QGuiApplication.instance() or QGuiApplication(["item-slot-interaction-perf"])
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))
    roots = engine.rootObjects()
    assert roots, "GraphicsEditor.qml did not load"
    root_object = roots[0]
    address = int(Shiboken.getCppPointer(root_object)[0])
    root = Shiboken.wrapInstance(address, QQuickWindow)
    assert root is not None and Shiboken.isValid(root)
    root.setProperty("showGrid", False)
    app.processEvents()
    QTest.qWait(120)
    app.processEvents()

    def quick_item(name: str) -> QQuickItem:
        obj = root.findChild(QObject, name)
        assert obj is not None, f"QML object not found: {name}"
        pointer = int(Shiboken.getCppPointer(obj)[0])
        item = Shiboken.wrapInstance(pointer, QQuickItem)
        assert item is not None and Shiboken.isValid(item), f"Invalid QQuickItem: {name}"
        return item

    def scene_center(item: QQuickItem) -> QPoint:
        point = item.mapToScene(QPointF(max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0))
        return QPoint(round(point.x()), round(point.y()))

    root_item = quick_item(f"sceneNode-{root_id}")
    child_item = quick_item(f"sceneNode-{child_id}")
    move_area = quick_item(f"itemSlotMoveArea-{slot_id}")
    move_start = scene_center(move_area)
    original_root_x = float(root_node.transform.x)
    original_child_x = float(child_node.transform.x)
    dispatch_before_move = len(bridge.commands)
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, move_start, 0)
    app.processEvents()
    move_samples: list[float] = []
    final_move = move_start
    preview_root_moved = False
    preview_child_moved = False
    backend_unchanged_during_move = True
    for index in range(1, 201):
        final_move = QPoint(move_start.x() + index, move_start.y() + round(index * 0.35))
        started = perf_counter_ns()
        QTest.mouseMove(root, final_move, 0)
        app.processEvents()
        move_samples.append((perf_counter_ns() - started) / 1_000_000.0)
        if index == 120:
            preview_root_moved = abs(float(root_item.x()) - original_root_x * float(root.property("zoom"))) > 2.0
            preview_child_moved = abs(float(child_item.x()) - original_child_x * float(root.property("zoom"))) > 2.0
            backend_unchanged_during_move = abs(float(root_node.transform.x) - original_root_x) < 1e-9
    move_dispatch_during_drag = len(bridge.commands) - dispatch_before_move
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_move, 0)
    app.processEvents()
    move_commits = len(bridge.commands) - dispatch_before_move
    assert move_dispatch_during_drag == 0
    assert move_commits == 1
    assert bridge.commands[-1].get("name") == "resize"
    assert preview_root_moved and preview_child_moved and backend_unchanged_during_move

    root_node = session.page.node(root_id)
    child_node = session.page.node(child_id)
    assert root_node is not None and child_node is not None
    moved_root_bounds = _round_bounds(root_node)
    moved_child_bounds = _round_bounds(child_node)
    assert moved_root_bounds != before_root_bounds
    assert moved_child_bounds != initial_child_bounds

    QTest.qWait(30)
    app.processEvents()
    resize_area = quick_item(f"itemSlotResizeArea-se-{slot_id}")
    resize_start = scene_center(resize_area)
    backend_width_before_resize = float(root_node.transform.width)
    visual_child_width_before_resize = float(child_item.width())
    dispatch_before_resize = len(bridge.commands)
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_start, 0)
    app.processEvents()
    resize_samples: list[float] = []
    final_resize = resize_start
    preview_child_resized = False
    backend_unchanged_during_resize = True
    for index in range(1, 201):
        final_resize = QPoint(resize_start.x() + round(index * 0.6), resize_start.y() + round(index * 0.45))
        started = perf_counter_ns()
        QTest.mouseMove(root, final_resize, 0)
        app.processEvents()
        resize_samples.append((perf_counter_ns() - started) / 1_000_000.0)
        if index == 120:
            preview_child_resized = abs(float(child_item.width()) - visual_child_width_before_resize) > 2.0
            backend_unchanged_during_resize = abs(float(root_node.transform.width) - backend_width_before_resize) < 1e-9
    resize_dispatch_during_drag = len(bridge.commands) - dispatch_before_resize
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_resize, 0)
    app.processEvents()
    resize_commits = len(bridge.commands) - dispatch_before_resize
    assert resize_dispatch_during_drag == 0
    assert resize_commits == 1
    assert bridge.commands[-1].get("name") == "resize"
    assert preview_child_resized and backend_unchanged_during_resize

    root_node = session.page.node(root_id)
    slot = session.page.slots[slot_id]
    assert root_node is not None
    after_snapshot = item_slot_snapshot(session.page, slot)
    relative_drift = _assert_role_relatives_preserved(before_snapshot, after_snapshot)
    assert relative_drift < 1e-6, relative_drift

    saved_bounds = {node_id: _round_bounds(node) for node_id, node in session.page.nodes.items() if node_id == root_id or node_id in session.page.descendants(root_id)}
    with TemporaryDirectory(prefix="srstudio-item-slot-perf-") as temp_dir:
        package_path = Path(temp_dir) / f"{preset_id}.srscene"
        save_package(session.document, package_path, embed_local_assets=True)
        reopened = load_package(package_path)
        reopened_page = reopened.active_page
        reopened_bounds = {
            node_id: _round_bounds(reopened_page.node(node_id))
            for node_id in saved_bounds
            if reopened_page.node(node_id) is not None
        }
        save_reopen_ok = reopened_bounds == saved_bounds and slot_id in reopened_page.slots
    assert save_reopen_ok

    evidence = {
        "preset_id": preset_id,
        "move": _summary(move_samples),
        "resize": _summary(resize_samples),
        "backend_dispatches_during_move": move_dispatch_during_drag,
        "backend_dispatches_during_resize": resize_dispatch_during_drag,
        "backend_commits_move_release": move_commits,
        "backend_commits_resize_release": resize_commits,
        "preview_root_moved": preview_root_moved,
        "preview_child_moved": preview_child_moved,
        "preview_child_resized": preview_child_resized,
        "backend_unchanged_during_move": backend_unchanged_during_move,
        "backend_unchanged_during_resize": backend_unchanged_during_resize,
        "preview_events": int(root.property("itemSlotPreviewEvents") or 0),
        "preview_updates": int(root.property("itemSlotPreviewUpdates") or 0),
        "backend_commits_qml": int(root.property("itemSlotBackendCommits") or 0),
        "last_commit_ms_qml": float(root.property("itemSlotLastCommitMs") or 0),
        "role_relative_max_drift": relative_drift,
        "save_reopen": save_reopen_ok,
        "root_bounds_before": before_root_bounds,
        "root_bounds_after_move": moved_root_bounds,
        "root_bounds_after_resize": _round_bounds(root_node),
        "dispatch_commands": [str(command.get("name") or "") for command in bridge.commands],
        "backend_dispatch_latency": _summary(bridge.dispatch_samples),
    }

    root.close()
    root_object.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen Windows benchmark for ItemSlot local preview interactions")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-qml", type=Path)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    qml_path = runtime_root / "_internal" / "srstudio" / "graphics2" / "qml" / "GraphicsEditor.qml"
    manifest_path = runtime_root / "graphics2-host-runtime.json"
    assert qml_path.is_file(), qml_path
    assert manifest_path.is_file(), manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relative_qml = "_internal/srstudio/graphics2/qml/GraphicsEditor.qml"
    runtime_hash = _sha256(qml_path)
    assert runtime_hash == _manifest_hash(manifest, relative_qml), "frozen QML hash mismatch"

    presets = [_run_preset(qml_path, preset_id) for preset_id in ("simples", "card", "destaque")]
    move_samples: list[float] = []
    resize_samples: list[float] = []
    for item in presets:
        # Reconstruct aggregate samples conservatively from per-preset summaries only for reporting.
        # Gate each preset independently below; aggregate is max-of-preset p95 and median-of-medians.
        move_samples.append(float(item["move"]["median_ms"]))
        resize_samples.append(float(item["resize"]["median_ms"]))

    result = {
        "schema": "srstudio/g2-item-slot-interaction-perf-1",
        "runtime_qml_sha256": runtime_hash,
        "runtime_manifest_hash_match": True,
        "baseline_contract": _legacy_contract(args.baseline_qml),
        "presets": presets,
        "overall": {
            "move_median_ms": round(float(median(move_samples)), 4),
            "move_p95_ms": round(max(float(item["move"]["p95_ms"]) for item in presets), 4),
            "resize_median_ms": round(float(median(resize_samples)), 4),
            "resize_p95_ms": round(max(float(item["resize"]["p95_ms"]) for item in presets), 4),
            "backend_dispatches_during_move": sum(int(item["backend_dispatches_during_move"]) for item in presets),
            "backend_dispatches_during_resize": sum(int(item["backend_dispatches_during_resize"]) for item in presets),
            "backend_commits_on_release": sum(int(item["backend_commits_move_release"]) + int(item["backend_commits_resize_release"]) for item in presets),
        },
    }

    baseline = result["baseline_contract"]
    if baseline.get("available"):
        assert baseline["generic_group_drag_target"] is True, baseline
        assert baseline["move_press_select_dispatch"] is True, baseline
        assert baseline["move_position_preview_handler"] is False, baseline
        assert baseline["resize_position_preview_handler"] is False, baseline
        assert baseline["item_slot_local_preview_present"] is False, baseline

    for item in presets:
        assert float(item["move"]["median_ms"]) < 1.0, item
        assert float(item["move"]["p95_ms"]) < 4.0, item
        assert float(item["resize"]["median_ms"]) < 1.0, item
        assert float(item["resize"]["p95_ms"]) < 4.0, item
        assert int(item["backend_dispatches_during_move"]) == 0, item
        assert int(item["backend_dispatches_during_resize"]) == 0, item
        assert int(item["backend_commits_move_release"]) == 1, item
        assert int(item["backend_commits_resize_release"]) == 1, item
        assert bool(item["preview_root_moved"]), item
        assert bool(item["preview_child_moved"]), item
        assert bool(item["preview_child_resized"]), item
        assert bool(item["save_reopen"]), item
        assert float(item["role_relative_max_drift"]) < 1e-6, item
        assert int(item["preview_events"]) >= 400, item
        assert 0 < int(item["preview_updates"]) <= int(item["preview_events"]), item
        assert int(item["backend_commits_qml"]) == 2, item

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
