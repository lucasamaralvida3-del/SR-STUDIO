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

    from PySide6.QtCore import QCoreApplication, QEvent, QObject, Property, QPoint, QPointF, Qt, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication, QMouseEvent
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
    app.processEvents(); QTest.qWait(180); app.processEvents()
    content_item = root.contentItem()
    assert content_item is not None

    def iter_visual(item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from iter_visual(child)

    def qvariant(value):
        return value.toVariant() if hasattr(value, "toVariant") else value

    def qml_map(value) -> dict:
        value = qvariant(value)
        return dict(value) if isinstance(value, dict) else {}

    def window_point(item: QQuickItem, x: float, y: float) -> QPoint:
        global_point = item.mapToGlobal(QPointF(x, y))
        return root.mapFromGlobal(QPoint(round(global_point.x()), round(global_point.y())))

    def center(item: QQuickItem) -> QPoint:
        return window_point(item, max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0)

    def diagnostic(item: QQuickItem) -> dict:
        scene = item.mapToScene(QPointF(0, 0))
        win = window_point(item, 0, 0)
        return {
            "name": str(item.objectName() or ""),
            "visible": bool(item.isVisible()),
            "enabled": bool(item.isEnabled()),
            "scene_x": float(scene.x()),
            "scene_y": float(scene.y()),
            "window_x": int(win.x()),
            "window_y": int(win.y()),
            "width": float(item.width()),
            "height": float(item.height()),
            "z": float(item.z()),
        }

    def quick_item(name: str, *, require_visible: bool = True) -> QQuickItem:
        matches = [item for item in iter_visual(content_item) if str(item.objectName() or "") == name]
        usable = [item for item in matches if item.isEnabled() and item.width() > 0 and item.height() > 0]
        active = [item for item in usable if item.isVisible()]
        selected = active if require_visible else usable
        if selected:
            return selected[-1]
        raise AssertionError({"missing": name, "candidates": [diagnostic(item) for item in matches]})

    def visual_rect(item: QQuickItem) -> dict[str, float]:
        point = item.mapToScene(QPointF(0, 0))
        return {"x": float(point.x()), "y": float(point.y()), "width": float(item.width()), "height": float(item.height())}

    def node_item(node_id: str) -> QQuickItem:
        candidates = []
        for item in iter_visual(content_item):
            data = qml_map(item.property("modelData"))
            display = qml_map(item.property("displayTransform"))
            if str(data.get("id") or "") == str(node_id) and all(key in display for key in ("x", "y", "width", "height")):
                candidates.append(item)
        active = [item for item in candidates if item.isVisible() and item.width() > 0 and item.height() > 0]
        if active or candidates:
            return (active or candidates)[-1]
        raise AssertionError(f"node delegate not found: {node_id}")

    def role_ids(snapshot: dict) -> dict[str, list[str]]:
        roles = snapshot["internal_roles"]
        price = snapshot["price_block"]
        return {
            "IMAGE": [str(roles["image"]["node_id"])],
            "NAME": [str(roles["name"]["node_id"])],
            "PRICE": [str(price[key]) for key in ("currency_node", "integer_node", "decimal_node") if price.get(key)],
            "UNIT": [str(roles["unit"]["node_id"])],
        }

    def capture_roles(ids: dict[str, list[str]]) -> dict[str, list[dict[str, float]]]:
        return {role: [visual_rect(node_item(node_id)) for node_id in node_ids] for role, node_ids in ids.items()}

    def rect_changed(left: dict[str, float], right: dict[str, float], tolerance: float = 0.75) -> bool:
        return any(abs(right[key] - left[key]) > tolerance for key in ("x", "y", "width", "height"))

    def rect_close(left: dict[str, float], right: dict[str, float], tolerance: float = 2.5) -> bool:
        return all(abs(right[key] - left[key]) <= tolerance for key in ("x", "y", "width", "height"))

    def assert_roles_changed(before, after) -> None:
        for role in ("IMAGE", "NAME", "PRICE", "UNIT"):
            assert before[role] and len(before[role]) == len(after[role]), role
            assert all(rect_changed(left, right) for left, right in zip(before[role], after[role])), role

    def assert_roles_close(before, after) -> None:
        for role in ("IMAGE", "NAME", "PRICE", "UNIT"):
            assert all(rect_close(left, right) for left, right in zip(before[role], after[role])), role

    def move_with_left(pos: QPoint, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(pos),
            QPointF(root.mapToGlobal(pos)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            modifiers,
        )
        QCoreApplication.sendEvent(root, event)

    slot = session.page.slots[slot_id]
    initial = item_slot_snapshot(session.page, slot)
    ids = role_ids(initial)
    root_id = str(initial["root_node_id"])
    semantic_contract = {
        "node_by_role": dict(slot.node_by_role),
        "price_block": dict(initial["price_block"]),
        "preset_id": initial["preset_id"],
    }

    roles_before_move = capture_roles(ids)
    root_before_move = visual_rect(node_item(root_id))
    frame_before_move = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    backend_before_move = item_slot_snapshot(session.page, slot)
    move_area = quick_item(f"smartSlotMoveArea-{slot_id}")
    move_start = center(move_area)
    dispatch_before_move = bridge.dispatch_count
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, move_start, 0)
    app.processEvents()
    assert bool(root.property("itemSlotPreviewActive"))
    assert str(root.property("itemSlotInteractionKind") or "") == "move"

    deadline = monotonic() + 3.05
    index = 0
    move_final = move_start
    while monotonic() < deadline:
        index += 1
        move_final = QPoint(move_start.x() + min(180, index), move_start.y() + min(95, index // 2))
        move_with_left(move_final)
        app.processEvents()
        if index in (1, 20, 80):
            assert bool(root.property("itemSlotPreviewActive")), f"MOVE preview canceled at event {index}"
        QTest.qWait(16)

    assert bool(root.property("itemSlotPreviewActive")), "MOVE preview canceled before release"
    assert bridge.dispatch_count == dispatch_before_move, bridge.commands
    assert item_slot_snapshot(session.page, slot) == backend_before_move, "backend changed during MOVE preview"
    preview_move = qml_map(root.property("itemSlotPreviewBounds"))
    roles_move_preview = capture_roles(ids)
    root_move_preview = visual_rect(node_item(root_id))
    frame_move_preview = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    assert_roles_changed(roles_before_move, roles_move_preview)
    assert rect_changed(root_before_move, root_move_preview)
    assert rect_changed(frame_before_move, frame_move_preview)

    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, move_final, 0)
    app.processEvents(); QTest.qWait(100); app.processEvents()
    assert bridge.dispatch_count == dispatch_before_move + 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    assert not bool(root.property("itemSlotPreviewActive"))
    after_move = item_slot_snapshot(session.page, slot)
    assert after_move["bounds"]["x"] == pytest.approx(float(preview_move["x"]), abs=1.0)
    assert after_move["bounds"]["y"] == pytest.approx(float(preview_move["y"]), abs=1.0)
    assert_roles_close(roles_move_preview, capture_roles(ids))

    root.setProperty("selectedSlotId", slot_id)
    app.processEvents(); QTest.qWait(120); app.processEvents()
    resize_area = quick_item(f"smartSlotResizeArea-se-{slot_id}")
    resize_start = center(resize_area)
    backend_before_resize = item_slot_snapshot(session.page, slot)
    roles_before_resize = capture_roles(ids)
    root_before_resize = visual_rect(node_item(root_id))
    overlay_before_resize = visual_rect(quick_item(f"smartSlotOverlay-{slot_id}"))
    physical_handle_before = visual_rect(quick_item(f"smartSlotHandle-se-{slot_id}"))
    visual_frame_before = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    visual_handle_before = visual_rect(quick_item(f"smartSlotVisualHandle-se-{slot_id}", require_visible=False))
    dispatch_before_resize = bridge.dispatch_count
    resize_events_before = int(root.property("itemSlotPreviewEvents") or 0)

    print("ITEMSLOT_RESIZE_TARGET=" + json.dumps({"target": diagnostic(resize_area), "window_point": {"x": resize_start.x(), "y": resize_start.y()}}, sort_keys=True), flush=True)
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_start, 0)
    app.processEvents()
    print("ITEMSLOT_RESIZE_PRESS=" + json.dumps({"preview_active": bool(root.property("itemSlotPreviewActive")), "kind": str(root.property("itemSlotInteractionKind") or ""), "pressed": bool(resize_area.property("pressed")), "contains_mouse": bool(resize_area.property("containsMouse"))}, sort_keys=True), flush=True)
    assert bool(root.property("itemSlotPreviewActive")), "RESIZE press did not activate preview"
    assert str(root.property("itemSlotInteractionKind") or "") == "resize"
    assert bool(resize_area.property("pressed")), "resize MouseArea does not own the press"

    deadline = monotonic() + 3.05
    index = 0
    resize_final = resize_start
    while monotonic() < deadline:
        index += 1
        resize_final = QPoint(resize_start.x() + min(160, index), resize_start.y() + min(120, round(index * 0.7)))
        move_with_left(resize_final)
        app.processEvents()
        if index in (1, 20, 80):
            assert bool(root.property("itemSlotPreviewActive")), f"RESIZE preview canceled at event {index}"
            assert bool(resize_area.property("pressed")), f"resize grab lost at event {index}"
        QTest.qWait(16)

    assert bool(root.property("itemSlotPreviewActive")), "RESIZE preview canceled before release"
    assert bool(resize_area.property("pressed")), "resize MouseArea lost grab before release"
    assert int(root.property("itemSlotPreviewEvents") or 0) > resize_events_before
    assert bridge.dispatch_count == dispatch_before_resize, bridge.commands
    assert item_slot_snapshot(session.page, slot) == backend_before_resize, "backend changed during RESIZE preview"
    preview_resize = qml_map(root.property("itemSlotPreviewBounds"))
    roles_resize_preview = capture_roles(ids)
    root_resize_preview = visual_rect(node_item(root_id))
    overlay_during_resize = visual_rect(quick_item(f"smartSlotOverlay-{slot_id}"))
    physical_handle_during = visual_rect(quick_item(f"smartSlotHandle-se-{slot_id}"))
    visual_frame_during = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    visual_handle_during = visual_rect(quick_item(f"smartSlotVisualHandle-se-{slot_id}"))
    assert_roles_changed(roles_before_resize, roles_resize_preview)
    assert rect_changed(root_before_resize, root_resize_preview)
    assert rect_close(overlay_before_resize, overlay_during_resize, 0.01), "interaction overlay moved during RESIZE"
    assert rect_close(physical_handle_before, physical_handle_during, 0.01), "physical handle moved during RESIZE"
    assert rect_changed(visual_frame_before, visual_frame_during), "visual frame did not follow RESIZE"
    assert rect_changed(visual_handle_before, visual_handle_during), "visual handle did not follow RESIZE"

    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_final, 0)
    app.processEvents(); QTest.qWait(120); app.processEvents()
    assert bridge.dispatch_count == dispatch_before_resize + 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    assert not bool(root.property("itemSlotPreviewActive"))
    final_snapshot = item_slot_snapshot(session.page, slot)
    assert final_snapshot["bounds"]["width"] == pytest.approx(float(preview_resize["width"]), abs=1.0)
    assert final_snapshot["bounds"]["height"] == pytest.approx(float(preview_resize["height"]), abs=1.0)
    assert_roles_close(roles_resize_preview, capture_roles(ids))

    root.setProperty("selectedSlotId", slot_id)
    app.processEvents(); QTest.qWait(100); app.processEvents()
    shift_area = quick_item(f"smartSlotResizeArea-se-{slot_id}")
    shift_start = center(shift_area)
    before_shift = item_slot_snapshot(session.page, slot)
    ratio_before = before_shift["bounds"]["width"] / before_shift["bounds"]["height"]
    shift_dispatch_before = bridge.dispatch_count
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, shift_start, 0)
    app.processEvents()
    assert bool(root.property("itemSlotPreviewActive"))
    assert bool(shift_area.property("pressed"))
    shift_final = QPoint(shift_start.x() + 65, shift_start.y() + 18)
    for step in range(1, 31):
        position = QPoint(
            shift_start.x() + round((shift_final.x() - shift_start.x()) * step / 30),
            shift_start.y() + round((shift_final.y() - shift_start.y()) * step / 30),
        )
        move_with_left(position, Qt.KeyboardModifier.ShiftModifier)
        app.processEvents(); QTest.qWait(5)
    assert bridge.dispatch_count == shift_dispatch_before
    assert bool(shift_area.property("pressed"))
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, shift_final, 0)
    app.processEvents(); QTest.qWait(100); app.processEvents()
    assert bridge.dispatch_count == shift_dispatch_before + 1
    after_shift = item_slot_snapshot(session.page, slot)
    ratio_after = after_shift["bounds"]["width"] / after_shift["bounds"]["height"]
    assert ratio_after == pytest.approx(ratio_before, rel=0.015)

    expected = item_slot_snapshot(session.page, slot)
    package = output_dir / "continuous-final.srscene"
    save_package(session.document, package, embed_local_assets=True)
    reopened = load_package(package, extract_assets_to=output_dir / "assets")
    restored_slot = reopened.active_page.slots[slot_id]
    restored = item_slot_snapshot(reopened.active_page, restored_slot)
    assert restored["bounds"] == expected["bounds"]
    assert restored["internal_roles"] == expected["internal_roles"]
    assert restored["price_block"] == expected["price_block"]
    assert restored["preset_id"] == expected["preset_id"]
    assert dict(restored_slot.node_by_role) == semantic_contract["node_by_role"]
    assert semantic_contract["price_block"] == expected["price_block"]
    assert semantic_contract["preset_id"] == expected["preset_id"]

    result = {
        "pass": True,
        "preset": "simples",
        "move_preview_active_until_release": True,
        "resize_preview_active_until_release": True,
        "mouse_grab_preserved": True,
        "unexpected_cancel": False,
        "backend_dispatches_during_move": 0,
        "backend_dispatches_during_resize": 0,
        "backend_commits_move_release": 1,
        "backend_commits_resize_release": 1,
        "interaction_overlay_stable_during_resize": True,
        "physical_handle_stable_during_resize": True,
        "visual_frame_followed_preview": True,
        "visual_handle_followed_preview": True,
        "image_preview": "PASS",
        "name_preview": "PASS",
        "price_preview": "PASS",
        "unit_preview": "PASS",
        "children_relative_alignment_preserved": True,
        "save_reopen_preserved": True,
        "shift_ratio_preserved": True,
        "commands": bridge.commands,
        "preview_events": int(root.property("itemSlotPreviewEvents") or 0),
        "preview_updates": int(root.property("itemSlotPreviewUpdates") or 0),
        "backend_commits_counter": int(root.property("itemSlotBackendCommits") or 0),
    }
    (output_dir / "continuous-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print("ITEMSLOT_CONTINUOUS_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    root.close(); root.deleteLater(); app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
