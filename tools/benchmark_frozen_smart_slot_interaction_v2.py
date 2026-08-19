from __future__ import annotations

import json
from time import perf_counter_ns

import benchmark_frozen_smart_slot_interaction as legacy


def _qml_benchmark(qml_path, output: dict) -> None:
    from shiboken6 import Shiboken
    from PySide6.QtCore import QObject, Property, QPoint, QPointF, Qt, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    document = legacy._document()
    session = legacy.GraphicsSession(document)
    router = legacy.GraphicsCommandRouter(session)

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "Smart Slot performance benchmark"
            self.dispatch_count = 0
            self.commit_samples: list[float] = []

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
            started = perf_counter_ns()
            result_raw = router.dispatch_json(raw, include_scene_payload=False)
            result = json.loads(result_raw)
            self.dispatch_count += 1
            self._status = str(result.get("message") or "")
            self.statusChanged.emit()
            self.sceneChanged.emit()
            self.commit_samples.append((perf_counter_ns() - started) / 1_000_000.0)
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

    app = QGuiApplication.instance() or QGuiApplication(["smart-slot-perf"])
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))
    roots = engine.rootObjects()
    assert roots, "GraphicsEditor.qml did not load"
    root = roots[0]
    root.setProperty("smartSlotEditMode", True)
    root.setProperty("smartSlotInspectionMode", True)
    root.setProperty("smartSlotSnap", False)
    root.setProperty("selectedSlotId", "slot-1")
    app.processEvents()
    QTest.qWait(250)
    app.processEvents()

    content_item = root.contentItem()
    assert content_item is not None, "ApplicationWindow has no contentItem"

    def iter_visual(item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from iter_visual(child)

    def quick_item(name: str) -> QQuickItem:
        for item in iter_visual(content_item):
            if str(item.objectName() or "") == name:
                return item
        available = sorted(
            str(item.objectName())
            for item in iter_visual(content_item)
            if str(item.objectName() or "").startswith("smartSlot")
        )
        raise AssertionError(f"QML visual item not found: {name}; available={available[:80]}")

    def scene_center(item: QQuickItem) -> QPoint:
        point = item.mapToScene(QPointF(max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0))
        return QPoint(round(point.x()), round(point.y()))

    move_area = quick_item("smartSlotMoveArea-slot-1")
    start = scene_center(move_area)
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start, 0)
    app.processEvents()
    move_samples: list[float] = []
    final_move = start
    for index in range(1, 121):
        final_move = QPoint(start.x() + index, start.y() + round(index * 0.45))
        started = perf_counter_ns()
        QTest.mouseMove(root, final_move, 0)
        app.processEvents()
        move_samples.append((perf_counter_ns() - started) / 1_000_000.0)
    release_started = perf_counter_ns()
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_move, 0)
    app.processEvents()
    move_release_ms = (perf_counter_ns() - release_started) / 1_000_000.0
    QTest.qWait(40)
    app.processEvents()

    root.setProperty("selectedSlotId", "slot-1")
    app.processEvents()
    QTest.qWait(40)
    app.processEvents()
    resize_area = quick_item("smartSlotResizeArea-se-slot-1")
    resize_start = scene_center(resize_area)
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_start, 0)
    app.processEvents()
    resize_samples: list[float] = []
    final_resize = resize_start
    for index in range(1, 101):
        final_resize = QPoint(resize_start.x() + index, resize_start.y() + round(index * 0.6))
        started = perf_counter_ns()
        QTest.mouseMove(root, final_resize, 0)
        app.processEvents()
        resize_samples.append((perf_counter_ns() - started) / 1_000_000.0)
    resize_release_started = perf_counter_ns()
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_resize, 0)
    app.processEvents()
    resize_release_ms = (perf_counter_ns() - resize_release_started) / 1_000_000.0
    QTest.qWait(40)
    app.processEvents()

    output["frozen_qml"] = {
        "move_event": legacy._summary(move_samples),
        "resize_event": legacy._summary(resize_samples),
        "move_release_ms": round(move_release_ms, 4),
        "resize_release_ms": round(resize_release_ms, 4),
        "backend_commit_in_dispatch": legacy._summary(bridge.commit_samples),
        "dispatch_count": bridge.dispatch_count,
        "preview_events": int(root.property("smartSlotPreviewEvents") or 0),
        "preview_updates": int(root.property("smartSlotPreviewUpdates") or 0),
        "last_commit_ms_qml": float(root.property("smartSlotLastCommitMs") or 0),
    }

    root.close()
    root.deleteLater()
    app.processEvents()


def main() -> int:
    legacy._qml_benchmark = _qml_benchmark
    return legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
