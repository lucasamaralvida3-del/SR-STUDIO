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
    app.processEvents()
    QTest.qWait(180)
    app.processEvents()
    content_item = root.contentItem()
    assert content_item is not None

    def iter_visual(item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from iter_visual(child)

    def qvariant(value):
        if hasattr(value, "toVariant"):
            return value.toVariant()
        return value

    def qml_map(value) -> dict:
        value = qvariant(value)
        return dict(value) if isinstance(value, dict) else {}

    def item_diagnostic(item: QQuickItem) -> dict:
        p = item.mapToScene(QPointF(0, 0))
        visible = bool(item.isVisible()) if hasattr(item, "isVisible") else bool(item.property("visible"))
        enabled = bool(item.isEnabled()) if hasattr(item, "isEnabled") else bool(item.property("enabled"))
        return {
            "object_name": str(item.objectName() or ""),
            "visible": visible,
            "enabled": enabled,
            "x": float(p.x()),
            "y": float(p.y()),
            "width": float(item.width()),
            "height": float(item.height()),
            "z": float(item.z()),
        }

    def quick_items(name: str) -> list[QQuickItem]:
        return [item for item in iter_visual(content_item) if str(item.objectName() or "") == name]

    def quick_item(name: str, *, require_visible: bool = True) -> QQuickItem:
        matches = quick_items(name)
        if not matches:
            raise AssertionError(f"QML item not found: {name}")
        active = []
        usable = []
        for item in matches:
            visible = bool(item.isVisible()) if hasattr(item, "isVisible") else bool(item.property("visible"))
            enabled = bool(item.isEnabled()) if hasattr(item, "isEnabled") else bool(item.property("enabled"))
            if enabled and float(item.width()) > 0 and float(item.height()) > 0:
                usable.append(item)
                if visible:
                    active.append(item)
        selected = active if require_visible else usable
        if len(matches) > 1 or (require_visible and len(active) != 1):
            print(
                "ITEMSLOT_QML_CANDIDATES="
                + json.dumps(
                    {
                        "name": name,
                        "matches": len(matches),
                        "active": len(active),
                        "usable": len(usable),
                        "require_visible": require_visible,
                        "items": [item_diagnostic(item) for item in matches],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
        if selected:
            # Scene refresh can leave an old delegate pending deletion for one
            # event turn. Repeater inserts the current delegate later, so use
            # the last usable candidate instead of the first objectName match.
            return selected[-1]
        raise AssertionError({"name": name, "require_visible": require_visible, "candidates": [item_diagnostic(item) for item in matches]})

    def center(item: QQuickItem) -> QPoint:
        p = item.mapToScene(QPointF(max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0))
        return QPoint(round(p.x()), round(p.y()))

    def inner_handle_point(item: QQuickItem, inset: float = 2.0) -> QPoint:
        p = item.mapToScene(QPointF(max(1.0, item.width()) / 2.0 - inset, max(1.0, item.height()) / 2.0 - inset))
        return QPoint(round(p.x()), round(p.y()))

    def visual_rect(item: QQuickItem) -> dict[str, float]:
        p = item.mapToScene(QPointF(0, 0))
        return {"x": float(p.x()), "y": float(p.y()), "width": float(item.width()), "height": float(item.height())}

    def node_item(node_id: str) -> QQuickItem:
        candidates = []
        for item in iter_visual(content_item):
            data = qml_map(item.property("modelData"))
            if str(data.get("id") or "") != str(node_id):
                continue
            display = qml_map(item.property("displayTransform"))
            if all(key in display for key in ("x", "y", "width", "height")):
                candidates.append(item)
        if not candidates:
            raise AssertionError(f"node delegate not found: {node_id}")
        active = [item for item in candidates if bool(item.isVisible()) and float(item.width()) > 0 and float(item.height()) > 0]
        return (active or candidates)[-1]

    def role_node_ids(snapshot: dict) -> dict[str, list[str]]:
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

    def rect_changed(before: dict[str, float], after: dict[str, float], tolerance: float = 0.75) -> bool:
        return any(abs(after[key] - before[key]) > tolerance for key in ("x", "y", "width", "height"))

    def rect_close(before: dict[str, float], after: dict[str, float], tolerance: float = 2.5) -> bool:
        return all(abs(after[key] - before[key]) <= tolerance for key in ("x", "y", "width", "height"))

    def assert_roles_changed(before, after) -> None:
        for role in ("IMAGE", "NAME", "PRICE", "UNIT"):
            assert len(before[role]) == len(after[role]) and before[role], role
            for left, right in zip(before[role], after[role]):
                assert rect_changed(left, right), {"role": role, "before": left, "after": right}

    def assert_roles_close(before, after) -> None:
        for role in ("IMAGE", "NAME", "PRICE", "UNIT"):
            for left, right in zip(before[role], after[role]):
                assert rect_close(left, right), {"role": role, "before": left, "after": right}

    def mouse_move_with_left_button(pos: QPoint, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        local = QPointF(pos)
        global_pos = QPointF(root.mapToGlobal(pos))
        event = QMouseEvent(QEvent.Type.MouseMove, local, global_pos, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, modifiers)
        QCoreApplication.sendEvent(root, event)

    slot = session.page.slots[slot_id]
    initial = item_slot_snapshot(session.page, slot)
    ids = role_node_ids(initial)
    root_id = str(initial["root_node_id"])
    semantics_before = {"node_by_role": dict(slot.node_by_role), "price_block": dict(initial["price_block"]), "preset_id": initial["preset_id"]}

    roles_before_move = capture_roles(ids)
    root_before_move = visual_rect(node_item(root_id))
    frame_before_move = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    handle_before_move = center(quick_item(f"smartSlotHandle-se-{slot_id}"))
    backend_before_move = item_slot_snapshot(session.page, slot)

    move_area = quick_item(f"smartSlotMoveArea-{slot_id}")
    start = center(move_area)
    before_dispatch = bridge.dispatch_count
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start, 0)
    app.processEvents()
    assert bool(root.property("itemSlotPreviewActive"))
    assert str(root.property("itemSlotInteractionKind") or "") == "move"
    deadline = monotonic() + 3.05
    index = 0
    final = start
    while monotonic() < deadline:
        index += 1
        final = QPoint(start.x() + min(180, index), start.y() + min(95, index // 2))
        mouse_move_with_left_button(final)
        app.processEvents()
        QTest.qWait(16)
    assert bool(root.property("itemSlotPreviewActive")), "MOVE preview canceled before release"
    assert bridge.dispatch_count == before_dispatch, bridge.commands
    assert item_slot_snapshot(session.page, slot) == backend_before_move, "backend changed during MOVE preview"
    preview_move = qml_map(root.property("itemSlotPreviewBounds"))
    roles_move_preview = capture_roles(ids)
    root_move_preview = visual_rect(node_item(root_id))
    frame_move_preview = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    handle_move_preview = center(quick_item(f"smartSlotHandle-se-{slot_id}"))
    assert_roles_changed(roles_before_move, roles_move_preview)
    assert rect_changed(root_before_move, root_move_preview)
    assert rect_changed(frame_before_move, frame_move_preview)
    assert handle_move_preview != handle_before_move

    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final, 0)
    app.processEvents(); QTest.qWait(80); app.processEvents()
    assert bridge.dispatch_count == before_dispatch + 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    assert not bool(root.property("itemSlotPreviewActive"))
    after_move = item_slot_snapshot(session.page, slot)
    assert after_move["bounds"]["x"] == pytest.approx(float(preview_move["x"]), abs=1.0)
    assert after_move["bounds"]["y"] == pytest.approx(float(preview_move["y"]), abs=1.0)
    assert_roles_close(roles_move_preview, capture_roles(ids))

    root.setProperty("selectedSlotId", slot_id)
    app.processEvents(); QTest.qWait(80); app.processEvents()
    resize_name = f"smartSlotResizeArea-se-{slot_id}"
    resize_area = quick_item(resize_name)
    resize_start = inner_handle_point(resize_area)
    backend_before_resize = item_slot_snapshot(session.page, slot)
    roles_before_resize = capture_roles(ids)
    root_before_resize = visual_rect(node_item(root_id))
    interaction_overlay_before = visual_rect(quick_item(f"smartSlotOverlay-{slot_id}"))
    interaction_handle_before = center(quick_item(f"smartSlotHandle-se-{slot_id}"))
    visual_frame_before = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    visual_handle_before = center(quick_item(f"smartSlotVisualHandle-se-{slot_id}", require_visible=False))
    before_resize_dispatch = bridge.dispatch_count
    before_resize_events = int(root.property("itemSlotPreviewEvents") or 0)
    print(
        "ITEMSLOT_RESIZE_TARGET="
        + json.dumps(
            {
                "target": item_diagnostic(resize_area),
                "target_point": {"x": resize_start.x(), "y": resize_start.y()},
                "handle": item_diagnostic(quick_item(f"smartSlotHandle-se-{slot_id}")),
                "move_area": item_diagnostic(quick_item(f"smartSlotMoveArea-{slot_id}")),
                "all_resize_candidates": [item_diagnostic(item) for item in quick_items(resize_name)],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_start, 0)
    app.processEvents()
    print(
        "ITEMSLOT_RESIZE_PRESS="
        + json.dumps(
            {
                "preview_active": bool(root.property("itemSlotPreviewActive")),
                "interaction_kind": str(root.property("itemSlotInteractionKind") or ""),
                "resize_pressed": bool(resize_area.property("pressed")),
                "resize_contains_mouse": bool(resize_area.property("containsMouse")),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    assert bool(root.property("itemSlotPreviewActive")), "RESIZE press did not activate preview"
    assert str(root.property("itemSlotInteractionKind") or "") == "resize"

    resize_deadline = monotonic() + 3.05
    resize_index = 0
    resize_final = resize_start
    while monotonic() < resize_deadline:
        resize_index += 1
        resize_final = QPoint(resize_start.x() + min(160, resize_index), resize_start.y() + min(120, round(resize_index * 0.7)))
        mouse_move_with_left_button(resize_final)
        app.processEvents()
        if resize_index == 1:
            assert bool(root.property("itemSlotPreviewActive")), "RESIZE preview canceled on first move"
        QTest.qWait(16)

    assert bool(root.property("itemSlotPreviewActive")), "RESIZE preview canceled before release"
    assert int(root.property("itemSlotPreviewEvents") or 0) > before_resize_events
    assert bridge.dispatch_count == before_resize_dispatch, bridge.commands
    assert item_slot_snapshot(session.page, slot) == backend_before_resize, "backend changed during RESIZE preview"
    preview_resize = qml_map(root.property("itemSlotPreviewBounds"))
    roles_resize_preview = capture_roles(ids)
    root_resize_preview = visual_rect(node_item(root_id))
    interaction_overlay_during = visual_rect(quick_item(f"smartSlotOverlay-{slot_id}"))
    interaction_handle_during = center(quick_item(f"smartSlotHandle-se-{slot_id}"))
    visual_frame_during = visual_rect(quick_item(f"smartSlotVisualFrame-{slot_id}"))
    visual_handle_during = center(quick_item(f"smartSlotVisualHandle-se-{slot_id}"))
    assert_roles_changed(roles_before_resize, roles_resize_preview)
    assert rect_changed(root_before_resize, root_resize_preview)
    assert rect_close(interaction_overlay_before, interaction_overlay_during, tolerance=0.01), "interaction overlay moved during RESIZE"
    assert interaction_handle_before == interaction_handle_during, "physical grab handle moved during RESIZE"
    assert rect_changed(visual_frame_before, visual_frame_during), "visual frame did not follow RESIZE preview"
    assert visual_handle_before != visual_handle_during, "visual handle did not follow RESIZE preview"

    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_final, 0)
    app.processEvents(); QTest.qWait(80); app.processEvents()
    assert bridge.dispatch_count == before_resize_dispatch + 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    assert not bool(root.property("itemSlotPreviewActive"))
    final_snapshot = item_slot_snapshot(session.page, slot)
    for key in ("x", "y", "width", "height"):
        assert final_snapshot["bounds"][key] == pytest.approx(float(preview_resize[key]), abs=1.0)
    assert_roles_close(roles_resize_preview, capture_roles(ids))

    root.setProperty("selectedSlotId", slot_id)
    app.processEvents(); QTest.qWait(60); app.processEvents()
    shift_start_snapshot = item_slot_snapshot(session.page, slot)
    shift_ratio = shift_start_snapshot["bounds"]["width"] / shift_start_snapshot["bounds"]["height"]
    shift_area = quick_item(f"smartSlotResizeArea-se-{slot_id}")
    shift_start = inner_handle_point(shift_area)
    before_shift_dispatch = bridge.dispatch_count
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, shift_start, 0)
    app.processEvents()
    assert bool(root.property("itemSlotPreviewActive"))
    shift_final = QPoint(shift_start.x() + 88, shift_start.y() + 31)
    for step in range(1, 61):
        pos = QPoint(shift_start.x() + round(88 * step / 60), shift_start.y() + round(31 * step / 60))
        mouse_move_with_left_button(pos, Qt.KeyboardModifier.ShiftModifier)
        app.processEvents()
    QTest.qWait(20); app.processEvents()
    shift_preview = qml_map(root.property("itemSlotPreviewBounds"))
    assert bridge.dispatch_count == before_shift_dispatch
    assert bool(root.property("itemSlotPreviewActive"))
    assert float(shift_preview["width"]) / float(shift_preview["height"]) == pytest.approx(shift_ratio, rel=0.01)
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, shift_final, 0)
    app.processEvents(); QTest.qWait(80); app.processEvents()
    assert bridge.dispatch_count == before_shift_dispatch + 1
    shift_final_snapshot = item_slot_snapshot(session.page, slot)
    assert shift_final_snapshot["bounds"]["width"] / shift_final_snapshot["bounds"]["height"] == pytest.approx(shift_ratio, rel=0.01)

    for role in initial["internal_roles"]:
        assert shift_final_snapshot["internal_roles"][role]["relative"] == pytest.approx(initial["internal_roles"][role]["relative"], abs=1e-8)
    assert dict(slot.node_by_role) == semantics_before["node_by_role"]
    assert shift_final_snapshot["price_block"] == semantics_before["price_block"]
    assert shift_final_snapshot["preset_id"] == semantics_before["preset_id"]

    package = output_dir / "item-slot-continuous-final.srscene"
    save_package(session.document, package, embed_local_assets=True)
    reopened = load_package(package, extract_assets_to=output_dir / "assets")
    restored_slot = reopened.active_page.slots[slot_id]
    reopened_snapshot = item_slot_snapshot(reopened.active_page, restored_slot)
    assert reopened_snapshot["bounds"] == shift_final_snapshot["bounds"]
    assert reopened_snapshot["internal_roles"] == shift_final_snapshot["internal_roles"]
    assert reopened_snapshot["price_block"] == shift_final_snapshot["price_block"]

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
        "shift_commit_on_release": 1,
        "preview_move_bounds": preview_move,
        "preview_resize_bounds": preview_resize,
        "final_bounds": shift_final_snapshot["bounds"],
        "interaction_overlay_stable": True,
        "mouse_grab_preserved": True,
        "preview_active_until_release": True,
        "visual_frame_follows_preview": True,
        "visual_handle_follows_preview": True,
        "image_preview": "PASS",
        "name_preview": "PASS",
        "price_preview": "PASS",
        "unit_preview": "PASS",
        "children_relative_alignment_preserved": True,
        "semantic_roles_preserved": True,
        "shift_ratio_preserved": True,
        "release_jump_within_tolerance": True,
        "save_reopen_preserved": True,
    }
    (output_dir / "continuous-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    root.close(); root.deleteLater(); app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
