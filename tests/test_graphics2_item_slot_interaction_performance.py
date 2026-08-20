from __future__ import annotations

# Exact-SHA certification contract for the ItemSlot local-preview performance path.
import json
from pathlib import Path

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import create_item_slot, item_slot_snapshot
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package


def _session() -> GraphicsSession:
    document = GraphicsDocument(name="ItemSlot interaction perf")
    document.add_page(GraphicsPage(name="Página 1", width=1080, height=1350))
    return GraphicsSession(document)


@pytest.mark.parametrize("preset_id", ["simples", "destaque", "card"])
def test_commit_item_slot_bounds_is_one_logical_group_commit_and_preserves_relative_children(preset_id: str) -> None:
    session = _session()
    slot = create_item_slot(session, preset_id, x=100, y=140)
    router = ItemSlotCommandRouter(session)
    root = session.page.node(str(slot.metadata["root_node_id"]))
    assert root is not None
    before = item_slot_snapshot(session.page, slot)

    result = router.dispatch(
        {
            "name": "commit_item_slot_bounds",
            "slot_id": slot.id,
            "x": root.transform.x + 37,
            "y": root.transform.y + 29,
            "width": root.transform.width * 1.18,
            "height": root.transform.height * 1.13,
        }
    )

    assert result.ok is True
    assert result.changed is True
    after = item_slot_snapshot(session.page, slot)
    assert after["bounds"] == result.payload["bounds"]
    assert after["preset_id"] == before["preset_id"]
    assert after["price_block"] == before["price_block"]
    assert set(after["internal_roles"]) == set(before["internal_roles"])
    for role in before["internal_roles"]:
        before_relative = before["internal_roles"][role]["relative"]
        after_relative = after["internal_roles"][role]["relative"]
        assert after_relative == pytest.approx(before_relative, abs=1e-9)

    assert session.undo() is True
    undone_slot = session.page.slots[slot.id]
    assert item_slot_snapshot(session.page, undone_slot) == before
    assert session.redo() is True
    redone_slot = session.page.slots[slot.id]
    assert item_slot_snapshot(session.page, redone_slot) == after


@pytest.mark.parametrize("preset_id", ["simples", "destaque", "card"])
def test_commit_item_slot_bounds_save_reopen_preserves_final_geometry(tmp_path: Path, preset_id: str) -> None:
    session = _session()
    slot = create_item_slot(session, preset_id, x=90, y=120)
    router = ItemSlotCommandRouter(session)
    root = session.page.node(str(slot.metadata["root_node_id"]))
    assert root is not None
    result = router.dispatch(
        {
            "name": "commit_item_slot_bounds",
            "slot_id": slot.id,
            "x": root.transform.x + 51,
            "y": root.transform.y + 43,
            "width": root.transform.width * 1.2,
            "height": root.transform.height * 1.15,
        }
    )
    assert result.ok and result.changed
    expected = item_slot_snapshot(session.page, slot)

    package = tmp_path / f"{preset_id}-interaction.srscene"
    save_package(session.document, package, embed_local_assets=True)
    reopened = load_package(package, extract_assets_to=tmp_path / f"{preset_id}-assets")
    restored_slot = reopened.active_page.slots[slot.id]
    actual = item_slot_snapshot(reopened.active_page, restored_slot)

    assert actual["bounds"] == expected["bounds"]
    assert actual["internal_roles"] == expected["internal_roles"]
    assert actual["preset_id"] == expected["preset_id"]


def test_qml_manual_item_slot_uses_direct_stable_resize_mousearea_and_one_release_command() -> None:
    qml = Path("src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    itemslot_region = qml[qml.index("model: slots()"):qml.index("id: selectionOverlay")]
    assert "property bool itemSlotPreviewActive: false" in qml
    assert "function itemSlotDisplayTransform(node)" in qml
    assert "property var displayTransform: window.itemSlotDisplayTransform(modelData)" in qml
    assert "property bool slotEditActive: isManualItemSlot || smartSlotEditMode" in qml
    assert 'var commandName = isManualItemSlot ? "commit_item_slot_bounds" : "adjust_smart_slot"' in qml
    assert "window.itemSlotBackendCommits += 1" in qml
    assert "drag.target: window.manualItemSlotForNode(modelData.id) ? null : parent" in qml
    assert "!window.manualItemSlotForNode(anchorNode.id)" in qml
    assert "if (slotMetadata.manual_item_slot)" in qml
    assert "root_node_id" in qml
    assert 'property bool resizePreviewKeepsInteractionGeometry: previewActive && isManualItemSlot && window.itemSlotInteractionKind === "resize"' in itemslot_region
    assert 'property var interactionBounds: resizePreviewKeepsInteractionGeometry ? bounds : displayBounds' in itemslot_region
    assert 'delegate: MouseArea {' in itemslot_region
    assert 'objectName: "smartSlotResizeArea-"' in itemslot_region
    assert 'acceptedButtons: Qt.LeftButton' in itemslot_region
    assert 'preventStealing: true' in itemslot_region
    assert 'objectName: "smartSlotHandle-"' in itemslot_region
    assert 'objectName: "smartSlotVisualHandle-"' in itemslot_region
    assert 'objectName: "smartSlotVisualFrame-"' in itemslot_region
    assert 'function resizedBounds(px, py, modifiers)' in itemslot_region
    assert 'slotOverlay.isManualItemSlot && (modifiers & Qt.ShiftModifier)' in itemslot_region
    assert 'id: slotResizeArea' not in itemslot_region
    assert 'manualItemSlotResizeHandler' not in itemslot_region
    assert 'DragHandler {' not in itemslot_region
    assert 'enabled: !slotOverlay.isManualItemSlot' not in itemslot_region

    # During manual resize the direct physical MouseArea and its ancestor stay on
    # the original interaction bounds. Only the independent visual handle/frame and
    # the ItemSlot subtree follow displayBounds / itemSlotDisplayTransform().
    assert "x: interactionBounds.x * zoom" in itemslot_region
    assert "width: interactionBounds.width * zoom" in itemslot_region
    assert "slotOverlay.displayBounds.x - slotOverlay.interactionBounds.x" in itemslot_region
    assert "modelData.fx * slotOverlay.displayBounds.width * zoom" in itemslot_region
    assert "property real desiredVisualX:" in itemslot_region
    assert "property real desiredVisualY:" in itemslot_region
    assert "Math.min(Math.max(0, slotOverlay.width - width)" in itemslot_region
    assert "Math.min(Math.max(0, slotOverlay.height - height)" in itemslot_region
    assert "visible: parent.visible" in itemslot_region
    assert "x: parent.desiredVisualX - parent.x" in itemslot_region
    assert "y: parent.desiredVisualY - parent.y" in itemslot_region
    assert "slotOverlay.queuePreview(resizedBounds(point.x, point.y, mouse.modifiers), false)" in itemslot_region
    assert "slotOverlay.commitPreview(resizedBounds(point.x, point.y, mouse.modifiers), \"resize\")" in itemslot_region


def test_direct_resize_mousearea_runtime_press_preview_grab_and_single_release_commit() -> None:
    from PySide6.QtCore import QCoreApplication, QEvent, QObject, Property, QPoint, QPointF, Qt, Signal, Slot, QUrl
    from PySide6.QtGui import QGuiApplication, QMouseEvent
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    session = _session()
    slot = create_item_slot(session, "simples", x=210, y=250)
    router = ItemSlotCommandRouter(session)

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self.dispatch_count = 0
            self._status = "direct resize focused runtime"

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
            self.dispatch_count += 1
            result_raw = router.dispatch_json(raw, include_scene_payload=False)
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

    app = QGuiApplication.instance() or QGuiApplication(["item-slot-direct-resize-focused"])
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml_path = Path("src/srstudio/graphics2/qml/GraphicsEditor.qml").resolve()
    engine.load(QUrl.fromLocalFile(str(qml_path)))
    roots = engine.rootObjects()
    assert roots
    root = roots[0]
    root.setProperty("smartSlotSnap", False)
    root.setProperty("selectedSlotId", slot.id)
    app.processEvents()
    QTest.qWait(120)
    app.processEvents()
    content = root.contentItem()
    assert content is not None

    def walk(item: QQuickItem):
        yield item
        for child in item.childItems():
            yield from walk(child)

    def cls(item: QQuickItem | None) -> str:
        return str(item.metaObject().className()) if item is not None else ""

    def prop(item: QQuickItem, key: str):
        value = item.property(key)
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        return str(value)

    name = f"smartSlotResizeArea-se-{slot.id}"
    candidates = [item for item in walk(content) if str(item.objectName() or "") == name]
    assert candidates
    resize_area = [item for item in candidates if item.isVisible() and item.isEnabled()][-1]
    assert resize_area.width() == pytest.approx(18.0)
    assert resize_area.height() == pytest.approx(18.0)
    local_center = QPointF(resize_area.width() / 2, resize_area.height() / 2)
    scene_center = resize_area.mapToScene(local_center)
    global_center = resize_area.mapToGlobal(local_center)
    center = root.mapFromGlobal(QPoint(round(global_center.x()), round(global_center.y())))
    parent_for_map = resize_area.parentItem()
    assert parent_for_map is not None
    to_parent = resize_area.mapToItem(parent_for_map, local_center)
    from_parent = resize_area.mapFromItem(parent_for_map, to_parent)

    parent_chain: list[dict] = []
    clipped_exclusions: list[dict] = []
    current: QQuickItem | None = resize_area
    while current is not None:
        local = current.mapFromScene(scene_center)
        child = current.childAt(local.x(), local.y())
        entry = {
            "class": cls(current),
            "name": str(current.objectName() or ""),
            "x": float(current.x()),
            "y": float(current.y()),
            "width": float(current.width()),
            "height": float(current.height()),
            "z": float(current.z()),
            "clip": bool(prop(current, "clip") or False),
            "visible": bool(current.isVisible()),
            "enabled": bool(current.isEnabled()),
            "opacity": float(current.opacity()),
            "point_local": {"x": float(local.x()), "y": float(local.y())},
            "contains_point": bool(current.contains(local)),
            "child_at": {"class": cls(child), "name": str(child.objectName() or "")} if child is not None else None,
        }
        parent_chain.append(entry)
        if entry["clip"] and not (0.0 <= local.x() <= current.width() and 0.0 <= local.y() <= current.height()):
            clipped_exclusions.append(entry)
        current = current.parentItem()

    topmost_chain: list[dict] = []
    current = content
    while current is not None:
        local = current.mapFromScene(scene_center)
        child = current.childAt(local.x(), local.y())
        topmost_chain.append({
            "owner": {"class": cls(current), "name": str(current.objectName() or "")},
            "local": {"x": float(local.x()), "y": float(local.y())},
            "child": {"class": cls(child), "name": str(child.objectName() or "")} if child is not None else None,
        })
        if child is None or child is current:
            break
        current = child

    focused_snapshot = {
        "target": {
            "class": cls(resize_area),
            "name": str(resize_area.objectName() or ""),
            "visible": bool(resize_area.isVisible()),
            "enabled": bool(resize_area.isEnabled()),
            "opacity": float(resize_area.opacity()),
            "accepted_buttons": prop(resize_area, "acceptedButtons"),
            "prevent_stealing": prop(resize_area, "preventStealing"),
            "propagate_composed_events": prop(resize_area, "propagateComposedEvents"),
            "contains_mouse": bool(prop(resize_area, "containsMouse") or False),
            "hovered": prop(resize_area, "hovered"),
            "clip": bool(prop(resize_area, "clip") or False),
            "z": float(resize_area.z()),
            "width": float(resize_area.width()),
            "height": float(resize_area.height()),
            "x": float(resize_area.x()),
            "y": float(resize_area.y()),
        },
        "local": {"x": float(local_center.x()), "y": float(local_center.y())},
        "scene": {"x": float(scene_center.x()), "y": float(scene_center.y())},
        "window": {"x": int(center.x()), "y": int(center.y())},
        "global": {"x": float(global_center.x()), "y": float(global_center.y())},
        "contains_local": bool(resize_area.contains(local_center)),
        "map_to_parent": {"x": float(to_parent.x()), "y": float(to_parent.y())},
        "map_from_parent_roundtrip": {"x": float(from_parent.x()), "y": float(from_parent.y())},
        "parent_chain": parent_chain,
        "topmost_chain": topmost_chain,
        "clipped_exclusions": clipped_exclusions,
    }
    print("ITEMSLOT_FOCUSED_HIT_TEST=" + json.dumps(focused_snapshot, sort_keys=True), flush=True)
    assert focused_snapshot["contains_local"] is True
    assert not clipped_exclusions

    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center, 0)
    app.processEvents()
    assert bool(resize_area.property("pressed")) is True
    assert bool(root.property("itemSlotPreviewActive")) is True
    assert str(root.property("itemSlotInteractionKind") or "") == "resize"
    assert bridge.dispatch_count == 0

    moved = QPoint(center.x() + 12, center.y() + 8)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(moved),
        QPointF(root.mapToGlobal(moved)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QCoreApplication.sendEvent(root, event)
    app.processEvents()
    QTest.qWait(20)
    app.processEvents()
    assert bool(resize_area.property("pressed")) is True
    assert bool(root.property("itemSlotPreviewActive")) is True
    assert int(root.property("itemSlotPreviewEvents") or 0) >= 1
    assert bridge.dispatch_count == 0

    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, moved, 0)
    app.processEvents()
    QTest.qWait(40)
    app.processEvents()
    assert bridge.dispatch_count == 1
    assert not bool(root.property("itemSlotPreviewActive"))
    assert int(root.property("itemSlotBackendCommits") or 0) == 1
    root.close()
    app.processEvents()
