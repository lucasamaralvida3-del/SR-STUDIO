from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import create_item_slot, item_slot_snapshot
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package

PRESETS = ("simples", "card", "destaque")
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


def _node_geometry(page: GraphicsPage, node_id: str) -> dict[str, float]:
    node = page.node(str(node_id))
    assert node is not None, node_id
    transform = node.transform
    return {
        "x": float(transform.x),
        "y": float(transform.y),
        "width": float(transform.width),
        "height": float(transform.height),
    }


def _run_preset(app, qml_path: Path, preset_id: str) -> dict:
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, Property, QPoint, QPointF, Qt, Signal, Slot, QUrl
    from PySide6.QtGui import QMouseEvent
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

    def qvariant(value):
        return value.toVariant() if hasattr(value, "toVariant") else value

    def qml_map(value) -> dict:
        value = qvariant(value)
        return dict(value) if isinstance(value, dict) else {}

    def class_name(item: QObject | None) -> str:
        if item is None:
            return ""
        try:
            return str(item.metaObject().className())
        except Exception:
            return type(item).__name__

    def property_value(item: QObject, name: str):
        try:
            value = qvariant(item.property(name))
            if value is None or isinstance(value, (bool, int, float, str)):
                return value
            return str(value)
        except Exception:
            return None

    def quick_item(name: str) -> QQuickItem:
        matches = [item for item in iter_visual(content_item) if str(item.objectName() or "") == name]
        usable = [
            item
            for item in matches
            if item.isVisible() and item.isEnabled() and item.width() > 0 and item.height() > 0
        ]
        if usable:
            return usable[-1]
        raise AssertionError(f"missing active QML item {name}")

    def active_node_item(node_id: str) -> QQuickItem:
        candidates: list[QQuickItem] = []
        for item in iter_visual(content_item):
            data = qml_map(item.property("modelData"))
            display = qml_map(item.property("displayTransform"))
            if str(data.get("id") or "") != str(node_id):
                continue
            if not all(key in display for key in ("x", "y", "width", "height")):
                continue
            candidates.append(item)
        active = [item for item in candidates if item.isVisible() and item.width() > 0 and item.height() > 0]
        if active or candidates:
            return (active or candidates)[-1]
        raise AssertionError(f"node delegate not found: {node_id}")

    def window_point(item: QQuickItem, x: float, y: float) -> QPoint:
        global_point = item.mapToGlobal(QPointF(x, y))
        return root.mapFromGlobal(QPoint(round(global_point.x()), round(global_point.y())))

    def scene_center(item: QQuickItem) -> QPoint:
        return window_point(item, max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0)

    def visual_rect(item: QQuickItem) -> dict[str, float]:
        point = item.mapToScene(QPointF(0, 0))
        return {
            "x": float(point.x()),
            "y": float(point.y()),
            "width": float(item.width()),
            "height": float(item.height()),
        }

    def clipped_exclusions(item: QQuickItem) -> list[dict]:
        local = QPointF(max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0)
        scene = item.mapToScene(local)
        result: list[dict] = []
        current = item.parentItem()
        while current is not None:
            if bool(property_value(current, "clip") or False):
                point = current.mapFromScene(scene)
                if not (0.0 <= point.x() <= current.width() and 0.0 <= point.y() <= current.height()):
                    result.append(
                        {
                            "class": class_name(current),
                            "name": str(current.objectName() or ""),
                            "local_x": float(point.x()),
                            "local_y": float(point.y()),
                            "width": float(current.width()),
                            "height": float(current.height()),
                        }
                    )
            current = current.parentItem()
        return result

    def reveal_in_clipped_flickables(item: QQuickItem, margin: float = 32.0) -> list[dict]:
        adjustments: list[dict] = []
        current = item.parentItem()
        while current is not None:
            content_x = property_value(current, "contentX")
            content_y = property_value(current, "contentY")
            is_flickable = "Flickable" in class_name(current) or (
                isinstance(content_x, (int, float)) and isinstance(content_y, (int, float))
            )
            if bool(property_value(current, "clip") or False) and is_flickable:
                local = item.mapToItem(
                    current,
                    QPointF(max(1.0, item.width()) / 2.0, max(1.0, item.height()) / 2.0),
                )
                before_x = float(content_x or 0.0)
                before_y = float(content_y or 0.0)
                target_x = before_x
                target_y = before_y
                if local.x() > current.width() - margin:
                    target_x += float(local.x() - (current.width() - margin))
                elif local.x() < margin:
                    target_x -= float(margin - local.x())
                if local.y() > current.height() - margin:
                    target_y += float(local.y() - (current.height() - margin))
                elif local.y() < margin:
                    target_y -= float(margin - local.y())
                content_width = property_value(current, "contentWidth")
                content_height = property_value(current, "contentHeight")
                max_x = (
                    max(0.0, float(content_width) - float(current.width()))
                    if isinstance(content_width, (int, float))
                    else max(0.0, target_x)
                )
                max_y = (
                    max(0.0, float(content_height) - float(current.height()))
                    if isinstance(content_height, (int, float))
                    else max(0.0, target_y)
                )
                target_x = max(0.0, min(max_x, target_x))
                target_y = max(0.0, min(max_y, target_y))
                if abs(target_x - before_x) > 0.01:
                    current.setProperty("contentX", target_x)
                if abs(target_y - before_y) > 0.01:
                    current.setProperty("contentY", target_y)
                if abs(target_x - before_x) > 0.01 or abs(target_y - before_y) > 0.01:
                    adjustments.append(
                        {
                            "class": class_name(current),
                            "name": str(current.objectName() or ""),
                            "before_content_x": before_x,
                            "before_content_y": before_y,
                            "after_content_x": target_x,
                            "after_content_y": target_y,
                        }
                    )
                    app.processEvents()
                    QTest.qWait(80)
                    app.processEvents()
            current = current.parentItem()
        return adjustments

    def tracked_ids(snapshot: dict) -> dict[str, list[str]]:
        roles = snapshot["internal_roles"]
        price = snapshot["price_block"]
        return {
            "IMAGE": [str(roles["image"]["node_id"])],
            "NAME": [str(roles["name"]["node_id"])],
            "PRICE": [str(price[key]) for key in ("currency_node", "integer_node", "decimal_node") if price.get(key)],
            "UNIT": [str(roles["unit"]["node_id"])],
        }

    def capture_roles(ids: dict[str, list[str]]) -> dict[str, list[dict[str, float]]]:
        return {
            role: [visual_rect(active_node_item(node_id)) for node_id in node_ids]
            for role, node_ids in ids.items()
        }

    def rect_changed(left: dict[str, float], right: dict[str, float], tolerance: float = 0.5) -> bool:
        return any(abs(right[key] - left[key]) > tolerance for key in ("x", "y", "width", "height"))

    def assert_roles_changed(before, after, phase: str) -> None:
        diagnostics: dict[str, list[dict]] = {}
        for role in ("IMAGE", "NAME", "PRICE", "UNIT"):
            assert before[role] and len(before[role]) == len(after[role]), {"phase": phase, "role": role}
            diagnostics[role] = []
            for left, right in zip(before[role], after[role]):
                changed = rect_changed(left, right)
                diagnostics[role].append({"before": left, "after": right, "changed": changed})
                assert changed, {"phase": phase, "role": role, "diagnostics": diagnostics}

    def mouse_move_with_left_button(pos: QPoint) -> None:
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(pos),
            QPointF(root.mapToGlobal(pos)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QCoreApplication.sendEvent(root, event)

    slot = session.page.slots[slot_id]
    before_move = item_slot_snapshot(session.page, slot)
    ids = tracked_ids(before_move)
    all_node_ids = sorted({node_id for node_ids in ids.values() for node_id in node_ids})
    roles_before_move = capture_roles(ids)
    move_area = quick_item(f"smartSlotMoveArea-{slot_id}")
    move_start = scene_center(move_area)
    dispatch_before_move = bridge.dispatch_count
    events_before_move = int(root.property("itemSlotPreviewEvents") or 0)

    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, move_start, 0)
    app.processEvents()
    assert bool(root.property("itemSlotPreviewActive"))
    dispatch_after_move_press = bridge.dispatch_count

    move_samples: list[float] = []
    final_move = move_start
    for index in range(1, EVENTS + 1):
        final_move = QPoint(
            move_start.x() + min(160, round(index * 0.8)),
            move_start.y() + min(90, round(index * 0.45)),
        )
        started = perf_counter_ns()
        mouse_move_with_left_button(final_move)
        app.processEvents()
        move_samples.append((perf_counter_ns() - started) / 1_000_000.0)
    QTest.qWait(32)
    app.processEvents()
    dispatch_before_move_release = bridge.dispatch_count
    events_after_move = int(root.property("itemSlotPreviewEvents") or 0)
    assert bool(root.property("itemSlotPreviewActive"))
    assert item_slot_snapshot(session.page, slot) == before_move
    roles_move_preview = capture_roles(ids)
    assert_roles_changed(roles_before_move, roles_move_preview, "MOVE")
    assert events_after_move - events_before_move >= EVENTS

    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_move, 0)
    app.processEvents()
    QTest.qWait(80)
    app.processEvents()
    dispatch_after_move_release = bridge.dispatch_count
    assert dispatch_after_move_press == dispatch_before_move
    assert dispatch_before_move_release == dispatch_before_move
    assert dispatch_after_move_release - dispatch_before_move_release == 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    after_move = item_slot_snapshot(session.page, slot)
    assert after_move["bounds"] != before_move["bounds"]

    root.setProperty("selectedSlotId", slot_id)
    app.processEvents()
    QTest.qWait(100)
    app.processEvents()
    resize_name = f"smartSlotResizeArea-se-{slot_id}"
    resize_area = quick_item(resize_name)
    pre_reveal_exclusions = clipped_exclusions(resize_area)
    resize_area = quick_item(resize_name)
    viewport_adjustments = reveal_in_clipped_flickables(resize_area)
    app.processEvents()
    QTest.qWait(100)
    app.processEvents()
    resize_area = quick_item(resize_name)
    post_reveal_exclusions = clipped_exclusions(resize_area)
    resize_area = quick_item(resize_name)
    assert not post_reveal_exclusions, {
        "preset": preset_id,
        "pre": pre_reveal_exclusions,
        "post": post_reveal_exclusions,
        "adjustments": viewport_adjustments,
    }

    resize_start = scene_center(resize_area)
    roles_before_resize = capture_roles(ids)
    backend_before_resize = item_slot_snapshot(session.page, slot)
    interaction_overlay_before = visual_rect(quick_item(f"smartSlotOverlay-{slot_id}"))
    dispatch_before_resize = bridge.dispatch_count
    events_before_resize = int(root.property("itemSlotPreviewEvents") or 0)

    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, resize_start, 0)
    app.processEvents()
    assert bool(root.property("itemSlotPreviewActive"))
    assert str(root.property("itemSlotInteractionKind") or "") == "resize"
    assert bool(resize_area.property("pressed"))
    dispatch_after_resize_press = bridge.dispatch_count

    resize_samples: list[float] = []
    final_resize = resize_start
    for index in range(1, EVENTS + 1):
        final_resize = QPoint(
            resize_start.x() + min(140, round(index * 0.7)),
            resize_start.y() + min(84, round(index * 0.42)),
        )
        started = perf_counter_ns()
        mouse_move_with_left_button(final_resize)
        app.processEvents()
        resize_samples.append((perf_counter_ns() - started) / 1_000_000.0)
    QTest.qWait(32)
    app.processEvents()
    dispatch_before_resize_release = bridge.dispatch_count
    events_after_resize = int(root.property("itemSlotPreviewEvents") or 0)
    assert bool(root.property("itemSlotPreviewActive"))
    assert bool(resize_area.property("pressed"))
    assert item_slot_snapshot(session.page, slot) == backend_before_resize
    roles_resize_preview = capture_roles(ids)
    assert_roles_changed(roles_before_resize, roles_resize_preview, "RESIZE")
    assert visual_rect(quick_item(f"smartSlotOverlay-{slot_id}")) == interaction_overlay_before
    assert events_after_resize - events_before_resize >= EVENTS

    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, final_resize, 0)
    app.processEvents()
    QTest.qWait(80)
    app.processEvents()
    dispatch_after_resize_release = bridge.dispatch_count
    resize_release_delta = dispatch_after_resize_release - dispatch_before_resize_release
    assert dispatch_after_resize_press == dispatch_before_resize
    assert dispatch_before_resize_release == dispatch_before_resize
    assert resize_release_delta == 1
    assert bridge.commands[-1] == "commit_item_slot_bounds"
    assert not bool(root.property("itemSlotPreviewActive"))

    final_snapshot = item_slot_snapshot(session.page, slot)
    final_node_by_role = dict(slot.node_by_role)
    final_node_geometry = {node_id: _node_geometry(session.page, node_id) for node_id in all_node_ids}

    with tempfile.TemporaryDirectory(prefix=f"itemslot-{preset_id}-") as tmp:
        tmp_path = Path(tmp)
        package = tmp_path / f"{preset_id}.srscene"
        save_package(session.document, package, embed_local_assets=True)
        reopened = load_package(package, extract_assets_to=tmp_path / "assets")
        restored = reopened.active_page.slots[slot_id]
        reopened_snapshot = item_slot_snapshot(reopened.active_page, restored)
        reopened_node_geometry = {
            node_id: _node_geometry(reopened.active_page, node_id) for node_id in all_node_ids
        }
        assert reopened_snapshot["bounds"] == final_snapshot["bounds"]
        assert reopened_snapshot["internal_roles"] == final_snapshot["internal_roles"]
        assert reopened_snapshot["price_block"] == final_snapshot["price_block"]
        assert reopened_snapshot["preset_id"] == final_snapshot["preset_id"]
        assert dict(restored.node_by_role) == final_node_by_role
        assert reopened_node_geometry == final_node_geometry
        for role, role_data in final_snapshot["internal_roles"].items():
            assert reopened_snapshot["internal_roles"][role]["relative"] == role_data["relative"]

    move_summary = _summary(move_samples)
    resize_summary = _summary(resize_samples)
    result = {
        "preset": preset_id,
        "move": move_summary,
        "resize": resize_summary,
        "move_preview_events": events_after_move - events_before_move,
        "resize_preview_events": events_after_resize - events_before_resize,
        "backend_dispatches_during_move": dispatch_before_move_release - dispatch_before_move,
        "backend_dispatches_during_resize": dispatch_before_resize_release - dispatch_before_resize,
        "backend_commits_move_release": dispatch_after_move_release - dispatch_before_move_release,
        "backend_commits_resize_release": resize_release_delta,
        "backend_commit_time": _summary(bridge.commit_samples_ms),
        "children_preview": {"IMAGE": "PASS", "NAME": "PASS", "PRICE": "PASS", "UNIT": "PASS"},
        "backend_model_unchanged_during_preview": True,
        "interaction_overlay_stable_during_resize": True,
        "resize_pressed": True,
        "pre_reveal_clipped_exclusions": pre_reveal_exclusions,
        "post_reveal_clipped_exclusions": post_reveal_exclusions,
        "viewport_reveal_adjustments": viewport_adjustments,
        "save_reopen": {
            "bounds": "PASS",
            "IMAGE": "PASS",
            "NAME": "PASS",
            "PRICE": "PASS",
            "UNIT": "PASS",
            "internal_roles": "PASS",
            "price_block": "PASS",
            "preset": "PASS",
            "node_by_role": "PASS",
            "relative_geometry": "PASS",
        },
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

    root.close()
    root.deleteLater()
    engine.deleteLater()
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
    total_preview_events = sum(
        int(item["move_preview_events"]) + int(item["resize_preview_events"]) for item in results
    )
    aggregate = {
        "move_median_max_ms": max(float(item["move"]["median_ms"]) for item in results),
        "move_p95_max_ms": max(float(item["move"]["p95_ms"]) for item in results),
        "resize_median_max_ms": max(float(item["resize"]["median_ms"]) for item in results),
        "resize_p95_max_ms": max(float(item["resize"]["p95_ms"]) for item in results),
        "backend_dispatches_during_move": sum(int(item["backend_dispatches_during_move"]) for item in results),
        "backend_dispatches_during_resize": sum(int(item["backend_dispatches_during_resize"]) for item in results),
        "backend_commits_move_release": sum(int(item["backend_commits_move_release"]) for item in results),
        "backend_commits_resize_release": sum(int(item["backend_commits_resize_release"]) for item in results),
        "preview_events": total_preview_events,
    }
    assert total_preview_events >= EVENTS * 2 * len(PRESETS), aggregate
    assert aggregate["backend_dispatches_during_move"] == 0
    assert aggregate["backend_dispatches_during_resize"] == 0
    assert aggregate["backend_commits_move_release"] == len(PRESETS)
    assert aggregate["backend_commits_resize_release"] == len(PRESETS)

    output = {
        "qml": str(qml_path),
        "events_per_interaction": EVENTS,
        "expected_total_preview_events": EVENTS * 2 * len(PRESETS),
        "thresholds_ms": {"median": 1.0, "p95": 4.0},
        "presets": results,
        "aggregate": aggregate,
        "all_roles_preview": True,
        "all_presets_save_reopen": True,
        "pass": True,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
