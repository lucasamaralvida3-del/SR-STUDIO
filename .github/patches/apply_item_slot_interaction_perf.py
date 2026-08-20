from __future__ import annotations

from pathlib import Path

TARGET = Path("src/srstudio/graphics2/qml/GraphicsEditor.qml")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


text = TARGET.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''    property string smartSlotInteractionKind: ""
    property var anchorNode: selectedNode()
''',
    '''    property string smartSlotInteractionKind: ""
    property bool itemSlotPreviewActive: false
    property string itemSlotPreviewRootId: ""
    property string itemSlotInteractionKind: ""
    property var itemSlotPreviewStartBounds: ({"x":0,"y":0,"width":1,"height":1})
    property var itemSlotPreviewBounds: ({"x":0,"y":0,"width":1,"height":1})
    property var itemSlotPendingPreviewBounds: ({"x":0,"y":0,"width":1,"height":1})
    property var itemSlotPreviewNodeIds: ({})
    property real itemSlotLastPreviewAppliedMs: 0
    property real itemSlotPreviewIntervalMs: 16
    property int itemSlotPreviewEvents: 0
    property int itemSlotPreviewUpdates: 0
    property int itemSlotBackendCommits: 0
    property real itemSlotLastCommitMs: 0
    property var anchorNode: selectedNode()
''',
    "preview-properties",
)

text = replace_once(
    text,
    '''    function hasCustomPath(node) {
        return !!(node && node.metadata && node.metadata.custom_path && node.metadata.custom_path.paths && node.metadata.custom_path.paths.length)
    }

    function slotBounds(slot) {
''',
    '''    function hasCustomPath(node) {
        return !!(node && node.metadata && node.metadata.custom_path && node.metadata.custom_path.paths && node.metadata.custom_path.paths.length)
    }

    function isManualItemSlotRoot(node) {
        return !!(node && node.kind === "group" && node.metadata && node.metadata.manual_item_slot_root === true)
    }

    function collectItemSlotPreviewNodes(rootId) {
        var result = ({})
        if (!page || !page.nodes || !rootId)
            return result
        var stack = [String(rootId)]
        var guard = 0
        while (stack.length && guard++ < 4096) {
            var nodeId = String(stack.pop() || "")
            if (!nodeId || result[nodeId])
                continue
            var node = page.nodes[nodeId]
            if (!node)
                continue
            result[nodeId] = true
            var children = node.children || []
            for (var i = 0; i < children.length; ++i)
                stack.push(String(children[i] || ""))
        }
        return result
    }

    function clampItemSlotPreview(raw) {
        var pageW = page ? Number(page.width || 1) : 1
        var pageH = page ? Number(page.height || 1) : 1
        var widthValue = Math.max(1, Math.min(Number(raw.width || 1), pageW))
        var heightValue = Math.max(1, Math.min(Number(raw.height || 1), pageH))
        var xValue = Math.max(0, Math.min(Number(raw.x || 0), Math.max(0, pageW - widthValue)))
        var yValue = Math.max(0, Math.min(Number(raw.y || 0), Math.max(0, pageH - heightValue)))
        return {"x":xValue,"y":yValue,"width":widthValue,"height":heightValue}
    }

    function beginItemSlotPreview(node, kind) {
        if (!isManualItemSlotRoot(node))
            return
        var t = node.transform
        var value = clampItemSlotPreview({
            "x":Number(t.x || 0),
            "y":Number(t.y || 0),
            "width":Math.max(1, Number(t.width || 1)),
            "height":Math.max(1, Number(t.height || 1))
        })
        itemSlotPreviewRootId = String(node.id || "")
        itemSlotPreviewNodeIds = collectItemSlotPreviewNodes(itemSlotPreviewRootId)
        itemSlotPreviewStartBounds = value
        itemSlotPreviewBounds = value
        itemSlotPendingPreviewBounds = value
        itemSlotLastPreviewAppliedMs = Date.now()
        itemSlotInteractionKind = String(kind || "")
        itemSlotPreviewActive = true
    }

    function queueItemSlotPreview(raw, force) {
        if (!itemSlotPreviewActive)
            return
        itemSlotPendingPreviewBounds = clampItemSlotPreview(raw)
        itemSlotPreviewEvents += 1
        var now = Date.now()
        if (force || itemSlotLastPreviewAppliedMs <= 0 || now - itemSlotLastPreviewAppliedMs >= itemSlotPreviewIntervalMs) {
            applyItemSlotPreview()
        } else if (!itemSlotPreviewTimer.running) {
            itemSlotPreviewTimer.start()
        }
    }

    function applyItemSlotPreview() {
        if (!itemSlotPreviewActive)
            return
        itemSlotPreviewBounds = itemSlotPendingPreviewBounds
        itemSlotLastPreviewAppliedMs = Date.now()
        itemSlotPreviewUpdates += 1
    }

    function itemSlotPreviewTransform(node) {
        var t = node ? node.transform : null
        if (!t || !itemSlotPreviewActive || !itemSlotPreviewNodeIds[String(node.id || "")])
            return t || {"x":0,"y":0,"width":1,"height":1,"rotation":0}
        var oldBounds = itemSlotPreviewStartBounds
        var newBounds = itemSlotPreviewBounds
        var oldW = Math.max(0.000001, Number(oldBounds.width || 1))
        var oldH = Math.max(0.000001, Number(oldBounds.height || 1))
        var sx = Number(newBounds.width || 1) / oldW
        var sy = Number(newBounds.height || 1) / oldH
        return {
            "x":Number(newBounds.x || 0) + (Number(t.x || 0) - Number(oldBounds.x || 0)) * sx,
            "y":Number(newBounds.y || 0) + (Number(t.y || 0) - Number(oldBounds.y || 0)) * sy,
            "width":Math.max(1, Number(t.width || 1) * sx),
            "height":Math.max(1, Number(t.height || 1) * sy),
            "rotation":Number(t.rotation || 0)
        }
    }

    function cancelItemSlotPreview() {
        itemSlotPreviewActive = false
        itemSlotPreviewTimer.stop()
        itemSlotPreviewRootId = ""
        itemSlotPreviewNodeIds = ({})
        itemSlotInteractionKind = ""
    }

    function commitItemSlotPreview(raw, kind) {
        if (!itemSlotPreviewActive || !itemSlotPreviewRootId)
            return
        queueItemSlotPreview(raw, true)
        var finalBounds = itemSlotPreviewBounds
        var rootId = itemSlotPreviewRootId
        var started = Date.now()
        itemSlotPreviewActive = false
        itemSlotPreviewTimer.stop()
        sceneBridge.dispatch(JSON.stringify({
            "name":"resize",
            "node_id":rootId,
            "x":finalBounds.x,
            "y":finalBounds.y,
            "width":finalBounds.width,
            "height":finalBounds.height,
            "min_size":1
        }))
        itemSlotBackendCommits += 1
        itemSlotLastCommitMs = Math.max(0, Date.now() - started)
        itemSlotInteractionKind = String(kind || "")
        itemSlotPreviewRootId = ""
        itemSlotPreviewNodeIds = ({})
    }

    function slotBounds(slot) {
''',
    "preview-functions",
)

text = replace_once(
    text,
    '''    Connections {
        target: sceneBridge
        function onSceneChanged() { window.refreshScene() }
    }
''',
    '''    Timer {
        id: itemSlotPreviewTimer
        interval: 16
        repeat: false
        onTriggered: window.applyItemSlotPreview()
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { window.refreshScene() }
    }
''',
    "preview-timer",
)

text = replace_once(
    text,
    '''                                delegate: Item {
                                    id: nodeItem
                                    required property var modelData
                                    x: modelData.transform.x * zoom
                                    y: modelData.transform.y * zoom
                                    width: Math.max(1, modelData.transform.width * zoom)
                                    height: Math.max(1, modelData.transform.height * zoom)
                                    rotation: Number(modelData.transform.rotation || 0)
                                    opacity: effectiveOpacity(modelData)
                                    visible: modelData.kind !== "group" || isSelected(modelData)
''',
    '''                                delegate: Item {
                                    id: nodeItem
                                    objectName: "sceneNode-" + String(modelData.id || "")
                                    required property var modelData
                                    property bool itemSlotPreviewMember: window.itemSlotPreviewActive && !!window.itemSlotPreviewNodeIds[String(modelData.id || "")]
                                    property var displayTransform: itemSlotPreviewMember ? window.itemSlotPreviewTransform(modelData) : modelData.transform
                                    x: displayTransform.x * zoom
                                    y: displayTransform.y * zoom
                                    width: Math.max(1, displayTransform.width * zoom)
                                    height: Math.max(1, displayTransform.height * zoom)
                                    rotation: Number(displayTransform.rotation || 0)
                                    opacity: effectiveOpacity(modelData)
                                    visible: modelData.kind !== "group" || isSelected(modelData)
''',
    "node-preview-transform",
)

text = replace_once(
    text,
    '''                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        drag.target: parent
                                        enabled: !effectiveLocked(modelData)
                                        preventStealing: true
                                        onPressed: sceneBridge.selectNodeAdvanced(modelData.id, (mouse.modifiers & Qt.ShiftModifier) !== 0, (mouse.modifiers & Qt.ControlModifier) !== 0)
                                        onReleased: {
                                            var dx = (parent.x / zoom) - Number(modelData.transform.x)
                                            var dy = (parent.y / zoom) - Number(modelData.transform.y)
                                            if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001)
                                                sceneBridge.moveSelectionAtZoom(dx, dy, zoom)
                                        }
                                        onDoubleClicked: if (modelData.kind === "text") textEditor.forceActiveFocus()
                                    }
''',
    '''                                    MouseArea {
                                        id: nodeMoveArea
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        property bool manualItemSlotRoot: window.isManualItemSlotRoot(modelData)
                                        property real itemSlotStartGlobalX: 0
                                        property real itemSlotStartGlobalY: 0
                                        property var itemSlotStartBounds: ({"x":0,"y":0,"width":1,"height":1})
                                        objectName: manualItemSlotRoot ? ("itemSlotMoveArea-" + String(modelData.metadata.item_slot_id || "")) : ""
                                        drag.target: manualItemSlotRoot ? null : parent
                                        enabled: !effectiveLocked(modelData)
                                        preventStealing: true
                                        onPressed: {
                                            if (manualItemSlotRoot && isSelected(modelData)) {
                                                var point = mapToItem(sheet, mouse.x, mouse.y)
                                                itemSlotStartGlobalX = point.x / zoom
                                                itemSlotStartGlobalY = point.y / zoom
                                                itemSlotStartBounds = {
                                                    "x":Number(modelData.transform.x || 0),
                                                    "y":Number(modelData.transform.y || 0),
                                                    "width":Math.max(1, Number(modelData.transform.width || 1)),
                                                    "height":Math.max(1, Number(modelData.transform.height || 1))
                                                }
                                                selectedSlotId = String(modelData.metadata.item_slot_id || selectedSlotId)
                                                window.beginItemSlotPreview(modelData, "move")
                                                return
                                            }
                                            sceneBridge.selectNodeAdvanced(modelData.id, (mouse.modifiers & Qt.ShiftModifier) !== 0, (mouse.modifiers & Qt.ControlModifier) !== 0)
                                        }
                                        onPositionChanged: {
                                            if (!pressed || !manualItemSlotRoot || !window.itemSlotPreviewActive)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            var dx = point.x / zoom - itemSlotStartGlobalX
                                            var dy = point.y / zoom - itemSlotStartGlobalY
                                            window.queueItemSlotPreview({
                                                "x":itemSlotStartBounds.x + dx,
                                                "y":itemSlotStartBounds.y + dy,
                                                "width":itemSlotStartBounds.width,
                                                "height":itemSlotStartBounds.height
                                            }, false)
                                        }
                                        onReleased: {
                                            if (manualItemSlotRoot && window.itemSlotPreviewActive) {
                                                var point = mapToItem(sheet, mouse.x, mouse.y)
                                                var dx = point.x / zoom - itemSlotStartGlobalX
                                                var dy = point.y / zoom - itemSlotStartGlobalY
                                                window.commitItemSlotPreview({
                                                    "x":itemSlotStartBounds.x + dx,
                                                    "y":itemSlotStartBounds.y + dy,
                                                    "width":itemSlotStartBounds.width,
                                                    "height":itemSlotStartBounds.height
                                                }, "move")
                                                return
                                            }
                                            var dx = (parent.x / zoom) - Number(modelData.transform.x)
                                            var dy = (parent.y / zoom) - Number(modelData.transform.y)
                                            if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001)
                                                sceneBridge.moveSelectionAtZoom(dx, dy, zoom)
                                        }
                                        onCanceled: if (manualItemSlotRoot) window.cancelItemSlotPreview()
                                        onDoubleClicked: if (modelData.kind === "text") textEditor.forceActiveFocus()
                                    }
''',
    "item-slot-move-area",
)

text = replace_once(
    text,
    '''                            Item {
                                id: selectionOverlay
                                visible: anchorNode && page && effectiveVisible(anchorNode)
                                x: visible ? anchorNode.transform.x * zoom : 0
                                y: visible ? anchorNode.transform.y * zoom : 0
                                width: visible ? Math.max(1, anchorNode.transform.width * zoom) : 1
                                height: visible ? Math.max(1, anchorNode.transform.height * zoom) : 1
                                rotation: visible ? Number(anchorNode.transform.rotation || 0) : 0
                                z: 200000
''',
    '''                            Item {
                                id: selectionOverlay
                                property bool itemSlotPreviewMember: !!anchorNode && window.itemSlotPreviewActive && window.itemSlotPreviewRootId === String(anchorNode.id || "")
                                property var displayTransform: itemSlotPreviewMember ? window.itemSlotPreviewTransform(anchorNode) : (anchorNode ? anchorNode.transform : {"x":0,"y":0,"width":1,"height":1,"rotation":0})
                                visible: anchorNode && page && effectiveVisible(anchorNode)
                                x: visible ? displayTransform.x * zoom : 0
                                y: visible ? displayTransform.y * zoom : 0
                                width: visible ? Math.max(1, displayTransform.width * zoom) : 1
                                height: visible ? Math.max(1, displayTransform.height * zoom) : 1
                                rotation: visible ? Number(displayTransform.rotation || 0) : 0
                                z: 200000
''',
    "selection-preview-transform",
)

text = replace_once(
    text,
    '''                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: modelData.cursor
                                            preventStealing: true
                                            property real pressX: 0
                                            property real pressY: 0
                                            onPressed: { pressX = mouse.x; pressY = mouse.y }
                                            onReleased: {
                                                if (!anchorNode) return
                                                sceneBridge.dispatch(JSON.stringify({
                                                    "name": "resize_handle",
                                                    "node_id": anchorNode.id,
                                                    "handle": modelData.dir,
                                                    "dx": (mouse.x - pressX) / zoom,
                                                    "dy": (mouse.y - pressY) / zoom,
                                                    "keep_ratio": (mouse.modifiers & Qt.ShiftModifier) !== 0
                                                }))
                                            }
                                        }
''',
    '''                                        MouseArea {
                                            id: selectionResizeArea
                                            anchors.fill: parent
                                            cursorShape: modelData.cursor
                                            preventStealing: true
                                            property real pressX: 0
                                            property real pressY: 0
                                            property real itemSlotStartGlobalX: 0
                                            property real itemSlotStartGlobalY: 0
                                            property real itemSlotStartX: 0
                                            property real itemSlotStartY: 0
                                            property real itemSlotStartW: 1
                                            property real itemSlotStartH: 1
                                            objectName: anchorNode && window.isManualItemSlotRoot(anchorNode)
                                                ? ("itemSlotResizeArea-" + String(modelData.dir) + "-" + String(anchorNode.metadata.item_slot_id || ""))
                                                : ""

                                            function itemSlotResizedBounds(px, py) {
                                                var dx = px / zoom - itemSlotStartGlobalX
                                                var dy = py / zoom - itemSlotStartGlobalY
                                                var nx = itemSlotStartX
                                                var ny = itemSlotStartY
                                                var nw = itemSlotStartW
                                                var nh = itemSlotStartH
                                                if (modelData.dir.indexOf("w") >= 0) { nx += dx; nw -= dx }
                                                if (modelData.dir.indexOf("e") >= 0) nw += dx
                                                if (modelData.dir.indexOf("n") >= 0) { ny += dy; nh -= dy }
                                                if (modelData.dir.indexOf("s") >= 0) nh += dy
                                                if (nw < 1) { if (modelData.dir.indexOf("w") >= 0) nx -= (1 - nw); nw = 1 }
                                                if (nh < 1) { if (modelData.dir.indexOf("n") >= 0) ny -= (1 - nh); nh = 1 }
                                                return {"x":nx,"y":ny,"width":nw,"height":nh}
                                            }

                                            onPressed: {
                                                if (!anchorNode)
                                                    return
                                                if (window.isManualItemSlotRoot(anchorNode)) {
                                                    var point = mapToItem(sheet, mouse.x, mouse.y)
                                                    itemSlotStartGlobalX = point.x / zoom
                                                    itemSlotStartGlobalY = point.y / zoom
                                                    itemSlotStartX = Number(anchorNode.transform.x || 0)
                                                    itemSlotStartY = Number(anchorNode.transform.y || 0)
                                                    itemSlotStartW = Math.max(1, Number(anchorNode.transform.width || 1))
                                                    itemSlotStartH = Math.max(1, Number(anchorNode.transform.height || 1))
                                                    window.beginItemSlotPreview(anchorNode, "resize")
                                                    return
                                                }
                                                pressX = mouse.x
                                                pressY = mouse.y
                                            }
                                            onPositionChanged: {
                                                if (!pressed || !anchorNode || !window.isManualItemSlotRoot(anchorNode) || !window.itemSlotPreviewActive)
                                                    return
                                                var point = mapToItem(sheet, mouse.x, mouse.y)
                                                window.queueItemSlotPreview(itemSlotResizedBounds(point.x, point.y), false)
                                            }
                                            onReleased: {
                                                if (!anchorNode)
                                                    return
                                                if (window.isManualItemSlotRoot(anchorNode) && window.itemSlotPreviewActive) {
                                                    var point = mapToItem(sheet, mouse.x, mouse.y)
                                                    window.commitItemSlotPreview(itemSlotResizedBounds(point.x, point.y), "resize")
                                                    return
                                                }
                                                sceneBridge.dispatch(JSON.stringify({
                                                    "name": "resize_handle",
                                                    "node_id": anchorNode.id,
                                                    "handle": modelData.dir,
                                                    "dx": (mouse.x - pressX) / zoom,
                                                    "dy": (mouse.y - pressY) / zoom,
                                                    "keep_ratio": (mouse.modifiers & Qt.ShiftModifier) !== 0
                                                }))
                                            }
                                            onCanceled: if (anchorNode && window.isManualItemSlotRoot(anchorNode)) window.cancelItemSlotPreview()
                                        }
''',
    "item-slot-resize-area",
)

TARGET.write_text(text, encoding="utf-8")
print(f"patched {TARGET}")
