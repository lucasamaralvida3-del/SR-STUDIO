from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_graphics_editor() -> None:
    path = ROOT / "src/srstudio/graphics2/qml/GraphicsEditor.qml"
    text = path.read_text(encoding="utf-8")
    old_props = """    property bool smartSlotSnap: true\n    property var anchorNode: selectedNode()\n"""
    new_props = """    property bool smartSlotSnap: true\n    property real smartSlotLastCommitMs: 0\n    property int smartSlotPreviewEvents: 0\n    property int smartSlotPreviewUpdates: 0\n    property string smartSlotInteractionKind: \"\"\n    property var anchorNode: selectedNode()\n"""
    if text.count(old_props) != 1:
        raise RuntimeError("GraphicsEditor.qml: Smart Slot property anchor changed")
    text = text.replace(old_props, new_props, 1)

    start_marker = "                            Repeater {\n                                model: slots()\n"
    end_marker = "\n                            Item {\n                                id: selectionOverlay"
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError("GraphicsEditor.qml: slots repeater start not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError("GraphicsEditor.qml: slots repeater end not found")

    replacement = r'''                            Repeater {
                                model: slots()
                                delegate: Item {
                                    id: slotOverlay
                                    objectName: "smartSlotOverlay-" + String(modelData.id || "")
                                    required property var modelData
                                    property var bounds: slotBounds(modelData)
                                    property var preview_bounds: ({"x": bounds.x, "y": bounds.y, "width": bounds.width, "height": bounds.height})
                                    property var pendingPreviewBounds: ({"x": bounds.x, "y": bounds.y, "width": bounds.width, "height": bounds.height})
                                    property bool previewActive: false
                                    property real lastPreviewAppliedMs: 0
                                    property int previewEventCount: 0
                                    property int previewUpdateCount: 0
                                    property real previewIntervalMs: 16
                                    property var displayBounds: previewActive ? preview_bounds : bounds
                                    property bool isDropTarget: productDragActive && dragHoverSlotId === modelData.id
                                    property bool isSelectedSlot: selectedSlotId === modelData.id
                                    property bool isHoveredSlot: hoveredSlotId === modelData.id
                                    property bool showSlotOverlay: smartSlotEditMode || smartSlotInspectionMode || productDragActive || isSelectedSlot || isHoveredSlot
                                    x: displayBounds.x * zoom
                                    y: displayBounds.y * zoom
                                    width: displayBounds.width * zoom
                                    height: displayBounds.height * zoom
                                    visible: showSlotOverlay && width > 2 && height > 2
                                    z: 100000

                                    function clampPreview(raw) {
                                        var pageW = page ? Number(page.width || 1) : 1
                                        var pageH = page ? Number(page.height || 1) : 1
                                        var widthValue = Math.max(1, Math.min(Number(raw.width || 1), pageW))
                                        var heightValue = Math.max(1, Math.min(Number(raw.height || 1), pageH))
                                        var xValue = Math.max(0, Math.min(Number(raw.x || 0), Math.max(0, pageW - widthValue)))
                                        var yValue = Math.max(0, Math.min(Number(raw.y || 0), Math.max(0, pageH - heightValue)))
                                        return {"x": xValue, "y": yValue, "width": widthValue, "height": heightValue}
                                    }

                                    function snapPreview(raw) {
                                        var value = clampPreview(raw)
                                        if (!smartSlotSnap || !scene.editor || !scene.editor.snap)
                                            return value
                                        var step = Math.max(0, Number(scene.editor.snap.grid_spacing || 0))
                                        if (step <= 0)
                                            return value
                                        var left = Math.round(value.x / step) * step
                                        var top = Math.round(value.y / step) * step
                                        var right = Math.round((value.x + value.width) / step) * step
                                        var bottom = Math.round((value.y + value.height) / step) * step
                                        return clampPreview({
                                            "x": left,
                                            "y": top,
                                            "width": Math.max(1, right - left),
                                            "height": Math.max(1, bottom - top)
                                        })
                                    }

                                    function beginPreview(raw, kind) {
                                        var value = snapPreview(raw)
                                        previewActive = true
                                        pendingPreviewBounds = value
                                        preview_bounds = value
                                        lastPreviewAppliedMs = Date.now()
                                        previewEventCount = 0
                                        previewUpdateCount = 0
                                        window.smartSlotInteractionKind = String(kind || "")
                                    }

                                    function queuePreview(raw, force) {
                                        if (!previewActive)
                                            return
                                        pendingPreviewBounds = snapPreview(raw)
                                        previewEventCount += 1
                                        window.smartSlotPreviewEvents += 1
                                        var now = Date.now()
                                        if (force || lastPreviewAppliedMs <= 0 || now - lastPreviewAppliedMs >= previewIntervalMs) {
                                            applyPendingPreview()
                                        } else if (!previewTimer.running) {
                                            previewTimer.start()
                                        }
                                    }

                                    function applyPendingPreview() {
                                        if (!previewActive)
                                            return
                                        preview_bounds = pendingPreviewBounds
                                        lastPreviewAppliedMs = Date.now()
                                        previewUpdateCount += 1
                                        window.smartSlotPreviewUpdates += 1
                                    }

                                    function commitPreview(raw, kind) {
                                        if (!previewActive)
                                            return
                                        queuePreview(raw, true)
                                        var finalBounds = preview_bounds
                                        var started = Date.now()
                                        sceneBridge.dispatch(JSON.stringify({
                                            "name":"adjust_smart_slot",
                                            "slot_id":slotOverlay.modelData.id,
                                            "x":finalBounds.x,
                                            "y":finalBounds.y,
                                            "width":finalBounds.width,
                                            "height":finalBounds.height,
                                            "snap":smartSlotSnap
                                        }))
                                        window.smartSlotLastCommitMs = Math.max(0, Date.now() - started)
                                        window.smartSlotInteractionKind = String(kind || "")
                                        previewActive = false
                                        previewTimer.stop()
                                    }

                                    Timer {
                                        id: previewTimer
                                        interval: 16
                                        repeat: false
                                        onTriggered: slotOverlay.applyPendingPreview()
                                    }

                                    Rectangle {
                                        anchors.fill: parent
                                        color: isDropTarget ? "#16A34A2A" : (isSelectedSlot ? "#0F5BD811" : (productDragActive ? "#0F5BD808" : "transparent"))
                                        border.width: isDropTarget ? 3 : (isSelectedSlot ? 2 : 1)
                                        border.color: isDropTarget ? "#16A34A" : (isSelectedSlot ? "#0F5BD8" : "#0F5BD855")
                                        radius: 4
                                    }
                                    Label {
                                        x: 4; y: 4
                                        text: isDropTarget ? "SOLTAR PRODUTO AQUI" : ((modelData.metadata && modelData.metadata.display_label) ? modelData.metadata.display_label : (modelData.name || "Smart Slot"))
                                        color: "white"
                                        font.bold: true
                                        font.pixelSize: 9
                                        padding: 3
                                        background: Rectangle { color: isDropTarget ? "#16A34A" : (isSelectedSlot ? "#0F5BD8" : "#64748BAA"); radius: 3 }
                                    }
                                    MouseArea {
                                        id: slotMoveArea
                                        objectName: "smartSlotMoveArea-" + String(slotOverlay.modelData.id || "")
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        hoverEnabled: true
                                        preventStealing: smartSlotEditMode
                                        property real startGlobalX: 0
                                        property real startGlobalY: 0
                                        property var startBounds: ({"x":0,"y":0,"width":1,"height":1})
                                        onEntered: hoveredSlotId = slotOverlay.modelData.id
                                        onExited: if (hoveredSlotId === slotOverlay.modelData.id) hoveredSlotId = ""
                                        onPressed: {
                                            selectedSlotId = slotOverlay.modelData.id
                                            if (!smartSlotEditMode)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            startGlobalX = point.x / zoom
                                            startGlobalY = point.y / zoom
                                            startBounds = {"x":slotOverlay.bounds.x,"y":slotOverlay.bounds.y,"width":slotOverlay.bounds.width,"height":slotOverlay.bounds.height}
                                            slotOverlay.beginPreview(startBounds, "move")
                                        }
                                        onClicked: selectedSlotId = slotOverlay.modelData.id
                                        onPositionChanged: {
                                            if (!pressed || !smartSlotEditMode || !slotOverlay.previewActive)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            var dx = point.x / zoom - startGlobalX
                                            var dy = point.y / zoom - startGlobalY
                                            slotOverlay.queuePreview({
                                                "x":startBounds.x + dx,
                                                "y":startBounds.y + dy,
                                                "width":startBounds.width,
                                                "height":startBounds.height
                                            }, false)
                                        }
                                        onReleased: {
                                            if (!smartSlotEditMode || !slotOverlay.previewActive)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            var dx = point.x / zoom - startGlobalX
                                            var dy = point.y / zoom - startGlobalY
                                            slotOverlay.commitPreview({
                                                "x":startBounds.x + dx,
                                                "y":startBounds.y + dy,
                                                "width":startBounds.width,
                                                "height":startBounds.height
                                            }, "move")
                                        }
                                        onCanceled: {
                                            slotOverlay.previewActive = false
                                            previewTimer.stop()
                                        }
                                    }
                                    Repeater {
                                        model: [
                                            {"dir":"nw","fx":0,"fy":0,"cursor":Qt.SizeFDiagCursor},
                                            {"dir":"n","fx":0.5,"fy":0,"cursor":Qt.SizeVerCursor},
                                            {"dir":"ne","fx":1,"fy":0,"cursor":Qt.SizeBDiagCursor},
                                            {"dir":"e","fx":1,"fy":0.5,"cursor":Qt.SizeHorCursor},
                                            {"dir":"se","fx":1,"fy":1,"cursor":Qt.SizeFDiagCursor},
                                            {"dir":"s","fx":0.5,"fy":1,"cursor":Qt.SizeVerCursor},
                                            {"dir":"sw","fx":0,"fy":1,"cursor":Qt.SizeBDiagCursor},
                                            {"dir":"w","fx":0,"fy":0.5,"cursor":Qt.SizeHorCursor}
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            objectName: "smartSlotHandle-" + String(modelData.dir) + "-" + String(slotOverlay.modelData.id || "")
                                            visible: smartSlotEditMode && slotOverlay.isSelectedSlot
                                            width: 11; height: 11; radius: 2
                                            x: modelData.fx * slotOverlay.width - width / 2
                                            y: modelData.fy * slotOverlay.height - height / 2
                                            color: "white"
                                            border.width: 2
                                            border.color: "#0F5BD8"
                                            z: 10
                                            MouseArea {
                                                id: slotResizeArea
                                                objectName: "smartSlotResizeArea-" + String(modelData.dir) + "-" + String(slotOverlay.modelData.id || "")
                                                anchors.fill: parent
                                                cursorShape: modelData.cursor
                                                preventStealing: true
                                                property real startGlobalX: 0
                                                property real startGlobalY: 0
                                                property real startX: 0
                                                property real startY: 0
                                                property real startW: 0
                                                property real startH: 0
                                                function resizedBounds(px, py) {
                                                    var dx = px / zoom - startGlobalX
                                                    var dy = py / zoom - startGlobalY
                                                    var nx = startX
                                                    var ny = startY
                                                    var nw = startW
                                                    var nh = startH
                                                    if (modelData.dir.indexOf("w") >= 0) { nx += dx; nw -= dx }
                                                    if (modelData.dir.indexOf("e") >= 0) nw += dx
                                                    if (modelData.dir.indexOf("n") >= 0) { ny += dy; nh -= dy }
                                                    if (modelData.dir.indexOf("s") >= 0) nh += dy
                                                    if (nw < 1) { if (modelData.dir.indexOf("w") >= 0) nx -= (1 - nw); nw = 1 }
                                                    if (nh < 1) { if (modelData.dir.indexOf("n") >= 0) ny -= (1 - nh); nh = 1 }
                                                    return {"x":nx,"y":ny,"width":nw,"height":nh}
                                                }
                                                onPressed: {
                                                    var point = mapToItem(sheet, mouse.x, mouse.y)
                                                    startGlobalX = point.x / zoom
                                                    startGlobalY = point.y / zoom
                                                    startX = slotOverlay.displayBounds.x
                                                    startY = slotOverlay.displayBounds.y
                                                    startW = slotOverlay.displayBounds.width
                                                    startH = slotOverlay.displayBounds.height
                                                    slotOverlay.beginPreview({"x":startX,"y":startY,"width":startW,"height":startH}, "resize")
                                                }
                                                onPositionChanged: {
                                                    if (!pressed || !slotOverlay.previewActive)
                                                        return
                                                    var point = mapToItem(sheet, mouse.x, mouse.y)
                                                    slotOverlay.queuePreview(resizedBounds(point.x, point.y), false)
                                                }
                                                onReleased: {
                                                    if (!slotOverlay.previewActive)
                                                        return
                                                    var point = mapToItem(sheet, mouse.x, mouse.y)
                                                    slotOverlay.commitPreview(resizedBounds(point.x, point.y), "resize")
                                                }
                                                onCanceled: {
                                                    slotOverlay.previewActive = false
                                                    previewTimer.stop()
                                                }
                                            }
                                        }
                                    }
                                }
                            }
'''
    text = text[:start] + replacement + text[end:]
    path.write_text(text, encoding="utf-8")


def patch_command_router() -> None:
    path = ROOT / "src/srstudio/graphics2/command_router.py"
    old = '''    def dispatch_json(self, raw: str) -> str:\n        try:\n            command = json.loads(raw)\n            if not isinstance(command, dict):\n                raise ValueError("Comando JSON deve ser um objeto.")\n            result = self.dispatch(command)\n        except Exception as exc:\n            result = CommandResult(False, False, f"Erro: {exc}")\n        result.payload = self.payload()\n        return json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":"))\n'''
    new = '''    def dispatch_json(self, raw: str, *, include_scene_payload: bool = True) -> str:\n        try:\n            command = json.loads(raw)\n            if not isinstance(command, dict):\n                raise ValueError("Comando JSON deve ser um objeto.")\n            result = self.dispatch(command)\n        except Exception as exc:\n            result = CommandResult(False, False, f"Erro: {exc}")\n        # QML already receives sceneJson through sceneChanged. Serializing the full\n        # document again into every command response doubles release-path work and\n        # used to discard command-specific payloads such as Smart Slot bounds.\n        if include_scene_payload:\n            result.payload = self.payload()\n        return json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":"))\n'''
    replace_once(path, old, new)


def patch_qt_host() -> None:
    path = ROOT / "src/srstudio/graphics2/qt_host.py"
    old = '''        @Slot(str, result=str)\n        def dispatch(self, payload: str) -> str:\n            result_raw = router.dispatch_json(payload)\n            try:\n'''
    new = '''        @Slot(str, result=str)\n        def dispatch(self, payload: str) -> str:\n            # sceneChanged publishes the canonical scene once after commit. Avoid\n            # embedding a second full-scene serialization in the synchronous QML\n            # command response, which is latency-sensitive on mouse release.\n            result_raw = router.dispatch_json(payload, include_scene_payload=False)\n            try:\n'''
    replace_once(path, old, new)


def patch_smart_slot_manual() -> None:
    path = ROOT / "src/srstudio/graphics2/smart_slot_manual.py"
    old = '''        slot.metadata["manual_adjustment_at"] = _timestamp()\n        slot.metadata["geometry_source"] = "manual"\n        _record_feedback(\n'''
    new = '''        slot.metadata["manual_adjustment_at"] = _timestamp()\n        slot.metadata["geometry_source"] = "manual"\n        # Overlap and drop-target invalidation are intentionally commit-on-release.\n        # No node scan or semantic rebuild is required while the pointer is moving.\n        overlap_ids = _slot_overlap_ids(page, slot, rect)\n        slot.metadata["manual_overlap_slot_ids"] = overlap_ids\n        slot.metadata["manual_overlap_count"] = len(overlap_ids)\n        page.metadata["drop_target_revision"] = int(page.metadata.get("drop_target_revision") or 0) + 1\n        _record_feedback(\n'''
    replace_once(path, old, new)

    anchor = '''def _intersection_area(a: Rect, b: Rect) -> float:\n'''
    helper = '''def _slot_overlap_ids(page: GraphicsPage, slot: SmartSlot, bounds: Rect) -> list[str]:\n    result: list[str] = []\n    for other in page.slots.values():\n        if other.id == slot.id:\n            continue\n        other_bounds = _effective_bounds(other) or _original_bounds(other)\n        if other_bounds is None:\n            continue\n        if _intersection_area(bounds, other_bounds) > 0:\n            result.append(other.id)\n    return sorted(result)\n\n\n'''
    text = path.read_text(encoding="utf-8")
    if text.count(anchor) != 1:
        raise RuntimeError("smart_slot_manual.py: intersection anchor changed")
    path.write_text(text.replace(anchor, helper + anchor, 1), encoding="utf-8")


def main() -> int:
    patch_graphics_editor()
    patch_command_router()
    patch_qt_host()
    patch_smart_slot_manual()
    print("SMART SLOT PERFORMANCE PATCH: APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
