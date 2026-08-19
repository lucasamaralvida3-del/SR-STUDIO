from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession


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


def _document(slot_count: int = 10) -> GraphicsDocument:
    page = GraphicsPage(id="page-perf", name="Perf 1080x1350", width=1080, height=1350)
    columns = 5
    for index in range(slot_count):
        row = index // columns
        col = index % columns
        x = 50 + col * 200
        y = 170 + row * 430
        slot_id = f"slot-{index + 1}"
        image = GraphicsNode(
            id=f"image-{index + 1}",
            kind=NodeKind.IMAGE,
            name=f"Imagem {index + 1}",
            transform=Transform(x=x + 18, y=y + 10, width=120, height=120),
        )
        name = GraphicsNode(
            id=f"name-{index + 1}",
            kind=NodeKind.TEXT,
            name=f"Nome {index + 1}",
            text=f"PRODUTO REAL {index + 1}",
            transform=Transform(x=x + 8, y=y + 145, width=170, height=34),
        )
        price_plate = GraphicsNode(
            id=f"plate-{index + 1}",
            kind=NodeKind.RECT,
            name=f"Price plate {index + 1}",
            transform=Transform(x=x + 20, y=y + 195, width=145, height=66),
            style={"fill": "#FFFFFF", "radius": 18},
        )
        price = GraphicsNode(
            id=f"price-{index + 1}",
            kind=NodeKind.TEXT,
            name=f"Preço {index + 1}",
            text=f"{index + 1}9,90",
            transform=Transform(x=x + 34, y=y + 208, width=96, height=40),
        )
        badge = GraphicsNode(
            id=f"badge-{index + 1}",
            kind=NodeKind.RECT,
            name=f"Badge {index + 1}",
            transform=Transform(x=x + 120, y=y + 16, width=58, height=28),
            style={"fill": "#FFFFFF", "radius": 14},
        )
        for node in (image, name, price_plate, price, badge):
            page.add_node(node)
        bounds = {"x": float(x), "y": float(y), "width": 185.0, "height": 285.0}
        page.slots[slot_id] = SmartSlot(
            id=slot_id,
            name=f"Produto {index + 1}",
            page_id=page.id,
            node_by_role={
                BindingRole.IMAGE.value: image.id,
                BindingRole.NAME.value: name.id,
                BindingRole.RETAIL_PRICE.value: price.id,
            },
            metadata={
                "source": "canva-smart-slot",
                "original_detected_bounds": dict(bounds),
                "effective_bounds": dict(bounds),
            },
        )
    return GraphicsDocument(id="doc-perf", name="Smart Slot perf", pages=[page], active_page_id=page.id)


def _percentile(samples: list[float], percentile: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _summary(samples: list[float]) -> dict[str, float]:
    return {
        "median_ms": round(float(median(samples)), 4) if samples else 0.0,
        "p95_ms": round(_percentile(samples, 0.95), 4),
        "max_ms": round(max(samples), 4) if samples else 0.0,
        "samples": len(samples),
    }


def _backend_commit_benchmark(samples: int = 40) -> dict:
    before: list[float] = []
    after: list[float] = []
    command = json.dumps(
        {"name": "adjust_smart_slot", "slot_id": "slot-1", "x": 72, "y": 182, "width": 205, "height": 300, "snap": False},
        separators=(",", ":"),
    )
    for _ in range(samples):
        document = _document()
        router = GraphicsCommandRouter(GraphicsSession(document))
        started = perf_counter_ns()
        router.dispatch_json(command, include_scene_payload=True)
        json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))
        before.append((perf_counter_ns() - started) / 1_000_000.0)

        document = _document()
        router = GraphicsCommandRouter(GraphicsSession(document))
        started = perf_counter_ns()
        router.dispatch_json(command, include_scene_payload=False)
        json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))
        after.append((perf_counter_ns() - started) / 1_000_000.0)
    return {"before": _summary(before), "after": _summary(after)}


def _legacy_contract(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {"available": False}
    text = path.read_text(encoding="utf-8")
    start = text.find("                            Repeater {\n                                model: slots()\n")
    end = text.find("\n                            Item {\n                                id: selectionOverlay", start)
    block = text[start:end] if start >= 0 and end > start else ""
    return {
        "available": bool(block),
        "uses_drag_target": "drag.target:" in block,
        "resize_position_changed_handlers": block.count("onPositionChanged:"),
        "resize_preview_present": "preview_bounds" in block,
        "adjust_dispatch_count": block.count('"name":"adjust_smart_slot"'),
    }


def _qml_benchmark(qml_path: Path, output: dict) -> None:
    from shiboken6 import Shiboken
    from PySide6.QtCore import QObject, Property, QPoint, QPointF, Qt, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QUrl

    document = _document()
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

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
    QTest.qWait(150)
    app.processEvents()

    def quick_item(name: str) -> QQuickItem:
        obj = root.findChild(QObject, name)
        assert obj is not None, f"QML object not found: {name}"
        address = int(Shiboken.getCppPointer(obj)[0])
        item = Shiboken.wrapInstance(address, QQuickItem)
        assert item is not None and Shiboken.isValid(item), f"Invalid QQuickItem: {name}"
        return item

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
        "move_event": _summary(move_samples),
        "resize_event": _summary(resize_samples),
        "move_release_ms": round(move_release_ms, 4),
        "resize_release_ms": round(resize_release_ms, 4),
        "backend_commit_in_dispatch": _summary(bridge.commit_samples),
        "dispatch_count": bridge.dispatch_count,
        "preview_events": int(root.property("smartSlotPreviewEvents") or 0),
        "preview_updates": int(root.property("smartSlotPreviewUpdates") or 0),
        "last_commit_ms_qml": float(root.property("smartSlotLastCommitMs") or 0),
    }

    root.close()
    root.deleteLater()
    app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-qml", type=Path)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    qml = runtime_root / "_internal" / "srstudio" / "graphics2" / "qml" / "GraphicsEditor.qml"
    manifest_path = runtime_root / "graphics2-host-runtime.json"
    assert qml.is_file(), qml
    assert manifest_path.is_file(), manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relative = "_internal/srstudio/graphics2/qml/GraphicsEditor.qml"
    qml_hash = _sha256(qml)
    assert qml_hash == _manifest_hash(manifest, relative), "frozen QML hash mismatch"

    result = {
        "schema": "srstudio/g2-smart-slot-interaction-perf-1",
        "runtime_qml_sha256": qml_hash,
        "runtime_manifest_hash_match": True,
        "legacy_contract": _legacy_contract(args.legacy_qml),
        "backend_release_commit": _backend_commit_benchmark(),
    }
    _qml_benchmark(qml, result)

    move = result["frozen_qml"]["move_event"]
    resize = result["frozen_qml"]["resize_event"]
    assert move["median_ms"] < 16.0, result
    assert resize["median_ms"] < 16.0, result
    assert move["p95_ms"] < 33.0, result
    assert resize["p95_ms"] < 33.0, result
    assert result["frozen_qml"]["dispatch_count"] == 2, result
    assert result["frozen_qml"]["preview_events"] >= 200, result
    assert result["frozen_qml"]["preview_updates"] > 0, result
    assert result["frozen_qml"]["preview_updates"] <= result["frozen_qml"]["preview_events"], result
    legacy = result["legacy_contract"]
    if legacy.get("available"):
        assert legacy["resize_preview_present"] is False, legacy
        assert legacy["resize_position_changed_handlers"] == 0, legacy
    before = result["backend_release_commit"]["before"]["median_ms"]
    after = result["backend_release_commit"]["after"]["median_ms"]
    assert after <= before * 1.10, result

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
