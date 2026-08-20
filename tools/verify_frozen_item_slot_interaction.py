from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import create_item_slot, item_slot_snapshot
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package


def _document() -> tuple[GraphicsDocument, str]:
    document = GraphicsDocument(name="Frozen ItemSlot continuous interaction")
    document.add_page(GraphicsPage(name="Página 1", width=1080, height=1350))
    session = GraphicsSession(document)
    slot = create_item_slot(session, "simples", x=210, y=250)
    return document, slot.id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qml", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    qml_path = Path(args.qml).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    assert qml_path.is_file(), qml_path

    from PySide6.QtCore import QObject, Property, QPoint, QPointF, Qt, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    document, slot_id = _document()
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = "Frozen ItemSlot continuous interaction"
            self.dispatch_count = 0
            self.commands: list[str] = []

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
            result_raw = router.dispatch_json(raw, include_scene_payload=False)
            result = json.loads(result_raw)
            self.dispatch_count += 1
            self.commands.append(str(command.get("name") or ""))
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

    app = QGuiApplication.instance() or QGuiApplication(["item-slot-continuous"])
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    roots = engine.rootObjects()
    assert roots, "frozen GraphicsEditor.qml did not load"
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
        raise AssertionError(f"QML item not found: {name}")

    def center(item: QQuickItem) -> QPoint:
        p = item.mapToScene(QPointF(max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0))
        return QPoint(round(p.x()), round(p.y()))

    def qml_map(value) -> dict:
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        return dict(value or {})

    def resize_state(label: str, before_events: int, before_commits: int) -> dict:
        state = {
            "label": label,
            "preview_active": bool(root.property("itemSlotPreviewActive")),
            "interaction_kind": str(root.property("itemSlotInteractionKind") or ""),
            "preview_events": int(root.property("itemSlotPreviewEvents") or 0),
            "preview_events_delta": int(root.property("itemSlotPreviewEvents") or 0) - before_events,
            "preview_updates": int(root.property("itemSlotPreviewUpdates") or 0),
            "backend_commits": int(root.property("itemSlotBackendCommits") or 0),
            "backend_commits_delta": int(root.property("itemSlotBackendCommits") or 0) - before_commits,
            "bridge_dispatches": bridge.dispatch_count,
            "commands": list(bridge.commands),
            "preview_bounds": qml_map(root.property("itemSlotPreviewBounds")),
        }
        print("ITEMSLOT_RESIZE_STATE=" + json.dumps(state, ensure_ascii=False, sort_keys=True), flush=True)
        return state

    slot = session.page.slots[slot_id]
    initial = item_slot_snapshot(session.page, slot)

    move_area = quick_item(f"smartSlotMoveArea-{slot_id}")
    start = center(move_area)
    before_dispatch = bridge.dispatch_count
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start, 0)
    app.processEvents()
    deadline = monotonic() + 3.05
    index = 0
    final = start
    while monotonic() < deadline:
        index += 1
        final = QPoint(start.x() + min(180, index), start.y() + min(95, index // 2))
        QTest.mouseMove(root, final, 0)
        app.processEvents()
        QTest.qWait(16)
    preview_move = qml_map(root.property("itemSlotPreviewBounds"))
    assert bridge.dispatch_count == before_dispatch, bridge.commands
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final, 0)
    app.processEvents()
    QTest.qWait(60)
    app.processEvents()
    assert bridge.dispatch_count == before_dispatch + 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    after_move = item_slot_snapshot(session.page, slot)
    assert after_move["bounds"]["x"] == pytest.approx(float(preview_move["x"]), abs=1.0)
    assert after_move["bounds"]["y"] == pytest.approx(float(preview_move["y"]), abs=1.0)

    root.setProperty("selectedSlotId", slot_id)
    app.processEvents()
    QTest.qWait(60)
    resize_area = quick_item(f"smartSlotResizeArea-se-{slot_id}")
    resize_start = center(resize_area)
    before_resize_dispatch = bridge.dispatch_count
    before_resize_events = int(root.property("itemSlotPreviewEvents") or 0)
    before_resize_commits = int(root.property("itemSlotBackendCommits") or 0)
    resize_state("before_press", before_resize_events, before_resize_commits)
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_start, 0)
    app.processEvents()
    resize_state("after_press", before_resize_events, before_resize_commits)
    resize_deadline = monotonic() + 3.05
    resize_index = 0
    resize_final = resize_start
    first_state = None
    while monotonic() < resize_deadline:
        resize_index += 1
        resize_final = QPoint(resize_start.x() + min(160, resize_index), resize_start.y() + min(120, round(resize_index * 0.7)))
        QTest.mouseMove(root, resize_final, 0)
        app.processEvents()
        if resize_index == 1:
            first_state = resize_state("after_first_move", before_resize_events, before_resize_commits)
        QTest.qWait(16)
    preview_resize = qml_map(root.property("itemSlotPreviewBounds"))
    before_release_state = resize_state("before_release", before_resize_events, before_resize_commits)
    assert bridge.dispatch_count == before_resize_dispatch, bridge.commands
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_final, 0)
    app.processEvents()
    QTest.qWait(60)
    app.processEvents()
    after_release_state = resize_state("after_release", before_resize_events, before_resize_commits)
    diagnostic = {
        "first_state": first_state,
        "before_release": before_release_state,
        "after_release": after_release_state,
        "expected_dispatches_after_release": before_resize_dispatch + 1,
        "actual_dispatches_after_release": bridge.dispatch_count,
    }
    assert bridge.dispatch_count == before_resize_dispatch + 1, diagnostic
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    final_snapshot = item_slot_snapshot(session.page, slot)
    for key in ("x", "y", "width", "height"):
        assert final_snapshot["bounds"][key] == pytest.approx(float(preview_resize[key]), abs=1.0)

    for role in initial["internal_roles"]:
        assert final_snapshot["internal_roles"][role]["relative"] == pytest.approx(initial["internal_roles"][role]["relative"], abs=1e-8)

    package = output_dir / "item-slot-continuous-final.srscene"
    save_package(session.document, package, embed_local_assets=True)
    reopened = load_package(package, extract_assets_to=output_dir / "assets")
    restored_slot = reopened.active_page.slots[slot_id]
    reopened_snapshot = item_slot_snapshot(reopened.active_page, restored_slot)
    assert reopened_snapshot["bounds"] == final_snapshot["bounds"]
    assert reopened_snapshot["internal_roles"] == final_snapshot["internal_roles"]

    result = {
        "pass": True,
        "preset": "simples",
        "move_duration_seconds": 3.05,
        "resize_duration_seconds": 3.05,
        "move_events": index,
        "resize_events": resize_index,
        "backend_dispatches_during_move": 0,
        "backend_dispatches_during_resize": 0,
        "backend_commits_on_move_release": 1,
        "backend_commits_on_resize_release": 1,
        "preview_move_bounds": preview_move,
        "preview_resize_bounds": preview_resize,
        "final_bounds": final_snapshot["bounds"],
        "children_relative_alignment_preserved": True,
        "save_reopen_preserved": True,
    }
    (output_dir / "continuous-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    root.close()
    root.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
