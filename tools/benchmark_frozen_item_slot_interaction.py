from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import create_item_slot, item_slot_snapshot
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession

PRESETS = ("simples", "destaque", "card")
EVENTS = 200
MOVE_MEDIAN_LIMIT_MS = 1.0
MOVE_P95_LIMIT_MS = 4.0
RESIZE_MEDIAN_LIMIT_MS = 1.0
RESIZE_P95_LIMIT_MS = 4.0


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return float(ordered[index])


def _summary(samples: list[float]) -> dict[str, float | int]:
    return {
        "median_ms": round(float(median(samples)), 4) if samples else 0.0,
        "p95_ms": round(_percentile(samples, 0.95), 4),
        "max_ms": round(max(samples), 4) if samples else 0.0,
        "samples": len(samples),
    }


def _document(preset_id: str) -> tuple[GraphicsDocument, str]:
    document = GraphicsDocument(name=f"ItemSlot perf {preset_id}")
    document.add_page(GraphicsPage(name="Página 1", width=1080, height=1350))
    session = GraphicsSession(document)
    slot = create_item_slot(session, preset_id, x=180, y=220)
    return document, slot.id


def _run_preset(app, qml_path: Path, preset_id: str) -> dict:
    from PySide6.QtCore import QObject, Property, QPoint, QPointF, Qt, Signal, Slot, QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    document, slot_id = _document(preset_id)
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "ItemSlot interaction benchmark"
            self.dispatch_count = 0
            self.commands: list[str] = []
            self.commit_samples_ms: list[float] = []

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return False

        @Slot(str, result=str)
        def dispatch(self, raw: str) -> str:
            command = json.loads(raw)
            started = perf_counter_ns()
            result_raw = router.dispatch_json(raw, include_scene_payload=False)
            self.commit_samples_ms.append((perf_counter_ns() - started) / 1_000_000.0)
            self.dispatch_count += 1
            self.commands.append(str(command.get("name") or ""))
            result = json.loads(result_raw)
            self._status = str(result.get("message") or "")
            self.statusChanged.emit()
            if result.get("changed"):
                self.sceneChanged.emit()
            return result_raw

        @Slot(str, bool, bool)
        def selectNodeAdvanced(self, _node_id: str, _additive: bool, _toggle: bool) -> None:
            return None

        @Slot(float, float, float)
        def moveSelectionAtZoom(self, _dx: float, _dy: float, _zoom: float) -> None:
            return None

        @Slot()
        def undo(self) -> None:
            return None

        @Slot()
        def redo(self) -> None:
            return None

        @Slot(str, str)
        def editText(self, _node_id: str, _text: str) -> None:
            return None

    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))
    roots = engine.rootObjects()
    assert roots, f"GraphicsEditor.qml failed to load for {preset_id}"
    root = roots[0]
    root.setProperty("smartSlotSnap", False)
    root.setProperty("selectedSlotId", slot_id)
    app.processEvents()
    QTest.qWait(180)
    app.processEvents()
    content_item = root.contentItem()
    assert content_item is not None

    def iter_visual(item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from iter_visual(child)

    def quick_item(name: str) -> QQuickItem:
        for item in iter_visual(content_item):
            if str(item.objectName() or "") == name:
                return item
        available = sorted(str(item.objectName() or "") for item in iter_visual(content_item) if str(item.objectName() or "").startswith("smartSlot"))
        raise AssertionError(f"missing QML item {name}; available={available[:100]}")

    def scene_center(item: QQuickItem) -> QPoint:
        p = item.mapToScene(QPointF(max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0))
        return QPoint(round(p.x()), round(p.y()))

    slot = session.page.slots[slot_id]
    before_move = item_slot_snapshot(session.page, slot)
    move_area = quick_item(f"smartSlotMoveArea-{slot_id}")
    move_start = scene_center(move_area)
    dispatch_before_move = bridge.dispatch_count
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, move_start, 0)
    app.processEvents()
    dispatch_after_press = bridge.dispatch_count
    move_samples: list[float] = []
    final_move = move_start
    for index in range(1, EVENTS + 1):
        final_move = QPoint(move_start.x() + index, move_start.y() + round(index * 0.35))
        started = perf_counter_ns()
        QTest.mouseMove(root, final_move, 0)
        app.processEvents()
        move_samples.append((perf_counter_ns() - started) / 1_000_000.0)
    dispatch_before_move_release = bridge.dispatch_count
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_move, 0)
    app.processEvents()
    QTest.qWait(50)
    app.processEvents()
    dispatch_after_move_release = bridge.dispatch_count
    assert dispatch_after_press == dispatch_before_move
    assert dispatch_before_move_release == dispatch_before_move
    assert dispatch_after_move_release - dispatch_before_move_release == 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    after_move = item_slot_snapshot(session.page, slot)
    assert after_move["bounds"] != before_move["bounds"]

    root.setProperty("selectedSlotId", slot_id)
    app.processEvents()
    QTest.qWait(50)
    app.processEvents()
    resize_area = quick_item(f"smartSlotResizeArea-se-{slot_id}")
    resize_start = scene_center(resize_area)
    dispatch_before_resize = bridge.dispatch_count
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_start, 0)
    app.processEvents()
    dispatch_after_resize_press = bridge.dispatch_count
    resize_samples: list[float] = []
    final_resize = resize_start
    for index in range(1, EVENTS + 1):
        final_resize = QPoint(resize_start.x() + index, resize_start.y() + round(index * 0.45))
        started = perf_counter_ns()
        QTest.mouseMove(root, final_resize, 0)
        app.processEvents()
        resize_samples.append((perf_counter_ns() - started) / 1_000_000.0)
    dispatch_before_resize_release = bridge.dispatch_count
    preview_active_before_release = bool(root.property("itemSlotPreviewActive"))
    preview_events_before_release = int(root.property("itemSlotPreviewEvents") or 0)
    preview_updates_before_release = int(root.property("itemSlotPreviewUpdates") or 0)
    backend_commits_before_release = int(root.property("itemSlotBackendCommits") or 0)
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_resize, 0)
    app.processEvents()
    QTest.qWait(50)
    app.processEvents()
    dispatch_after_resize_release = bridge.dispatch_count
    resize_release_delta = dispatch_after_resize_release - dispatch_before_resize_release
    diagnostic = {
        "preset": preset_id,
        "dispatch_before_resize": dispatch_before_resize,
        "dispatch_after_resize_press": dispatch_after_resize_press,
        "dispatch_before_resize_release": dispatch_before_resize_release,
        "dispatch_after_resize_release": dispatch_after_resize_release,
        "resize_release_delta": resize_release_delta,
        "preview_active_before_release": preview_active_before_release,
        "preview_active_after_release": bool(root.property("itemSlotPreviewActive")),
        "preview_events_before_release": preview_events_before_release,
        "preview_updates_before_release": preview_updates_before_release,
        "backend_commits_before_release": backend_commits_before_release,
        "backend_commits_after_release": int(root.property("itemSlotBackendCommits") or 0),
        "commands": list(bridge.commands),
    }
    print("ITEMSLOT_RESIZE_RELEASE_DIAGNOSTIC=" + json.dumps(diagnostic, ensure_ascii=False, sort_keys=True), flush=True)
    assert dispatch_after_resize_press == dispatch_before_resize, diagnostic
    assert dispatch_before_resize_release == dispatch_before_resize, diagnostic
    assert resize_release_delta == 1, diagnostic
    assert bridge.commands[-1] == "commit_item_slot_bounds", diagnostic

    move_summary = _summary(move_samples)
    resize_summary = _summary(resize_samples)
    result = {
        "preset": preset_id,
        "move": move_summary,
        "resize": resize_summary,
        "backend_dispatches_during_move": dispatch_before_move_release - dispatch_before_move,
        "backend_dispatches_during_resize": dispatch_before_resize_release - dispatch_before_resize,
        "backend_commits_move_release": dispatch_after_move_release - dispatch_before_move_release,
        "backend_commits_resize_release": resize_release_delta,
        "itemslot_preview_events": int(root.property("itemSlotPreviewEvents") or 0),
        "itemslot_preview_updates": int(root.property("itemSlotPreviewUpdates") or 0),
        "itemslot_backend_commits": int(root.property("itemSlotBackendCommits") or 0),
        "backend_commit_time": _summary(bridge.commit_samples_ms),
    }
    assert int(move_summary["samples"]) == EVENTS
    assert int(resize_summary["samples"]) == EVENTS
    assert float(move_summary["median_ms"]) < MOVE_MEDIAN_LIMIT_MS, move_summary
    assert float(move_summary["p95_ms"]) < MOVE_P95_LIMIT_MS, move_summary
    assert float(resize_summary["median_ms"]) < RESIZE_MEDIAN_LIMIT_MS, resize_summary
    assert float(resize_summary["p95_ms"]) < RESIZE_P95_LIMIT_MS, resize_summary
    assert result["backend_dispatches_during_move"] == 0
    assert result["backend_dispatches_during_resize"] == 0
    assert result["backend_commits_move_release"] == 1
    assert result["backend_commits_resize_release"] == 1
    assert result["itemslot_backend_commits"] == 2
    assert result["itemslot_preview_events"] >= EVENTS * 2
    assert result["itemslot_preview_updates"] <= result["itemslot_preview_events"]

    root.close()
    root.deleteLater()
    app.processEvents()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qml", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    qml_path = Path(args.qml).resolve()
    assert qml_path.is_file(), qml_path

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(["item-slot-perf"])
    results = [_run_preset(app, qml_path, preset) for preset in PRESETS]
    aggregate = {
        "move_median_max_ms": max(float(item["move"]["median_ms"]) for item in results),
        "move_p95_max_ms": max(float(item["move"]["p95_ms"]) for item in results),
        "resize_median_max_ms": max(float(item["resize"]["median_ms"]) for item in results),
        "resize_p95_max_ms": max(float(item["resize"]["p95_ms"]) for item in results),
        "backend_dispatches_during_move": sum(int(item["backend_dispatches_during_move"]) for item in results),
        "backend_dispatches_during_resize": sum(int(item["backend_dispatches_during_resize"]) for item in results),
        "backend_commits_on_release": sum(int(item["backend_commits_move_release"]) + int(item["backend_commits_resize_release"]) for item in results),
    }
    output = {
        "qml": str(qml_path),
        "events_per_interaction": EVENTS,
        "thresholds_ms": {"median": 1.0, "p95": 4.0},
        "presets": results,
        "aggregate": aggregate,
        "pass": True,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
