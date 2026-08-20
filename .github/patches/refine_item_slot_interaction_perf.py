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
    '''    function clampItemSlotPreview(raw) {
        var pageW = page ? Number(page.width || 1) : 1
        var pageH = page ? Number(page.height || 1) : 1
        var widthValue = Math.max(1, Math.min(Number(raw.width || 1), pageW))
        var heightValue = Math.max(1, Math.min(Number(raw.height || 1), pageH))
        var xValue = Math.max(0, Math.min(Number(raw.x || 0), Math.max(0, pageW - widthValue)))
        var yValue = Math.max(0, Math.min(Number(raw.y || 0), Math.max(0, pageH - heightValue)))
        return {"x":xValue,"y":yValue,"width":widthValue,"height":heightValue}
    }
''',
    '''    function clampItemSlotPreview(raw) {
        // Match the existing generic editor semantics: move/resize are not page-clamped.
        return {
            "x":Number(raw.x || 0),
            "y":Number(raw.y || 0),
            "width":Math.max(1, Number(raw.width || 1)),
            "height":Math.max(1, Number(raw.height || 1))
        }
    }
''',
    "preserve-unclamped-editor-semantics",
)

text = replace_once(
    text,
    '''        var started = Date.now()
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
''',
    '''        var started = Date.now()
        itemSlotPreviewTimer.stop()
        // Keep the local preview visible while the synchronous final transaction
        // rebuilds the scene so release cannot flash back to stale backend geometry.
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
        itemSlotPreviewActive = false
        itemSlotPreviewRootId = ""
        itemSlotPreviewNodeIds = ({})
''',
    "keep-preview-through-release-dispatch",
)

text = replace_once(
    text,
    '''                                            function itemSlotResizedBounds(px, py) {
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
''',
    '''                                            function itemSlotResizedBounds(px, py, keepRatio) {
                                                var dx = px / zoom - itemSlotStartGlobalX
                                                var dy = py / zoom - itemSlotStartGlobalY
                                                var right = itemSlotStartX + itemSlotStartW
                                                var bottom = itemSlotStartY + itemSlotStartH
                                                var nx = itemSlotStartX
                                                var ny = itemSlotStartY
                                                var nr = right
                                                var nb = bottom
                                                if (modelData.dir.indexOf("w") >= 0) nx = Math.min(right - 1, itemSlotStartX + dx)
                                                if (modelData.dir.indexOf("e") >= 0) nr = Math.max(itemSlotStartX + 1, right + dx)
                                                if (modelData.dir.indexOf("n") >= 0) ny = Math.min(bottom - 1, itemSlotStartY + dy)
                                                if (modelData.dir.indexOf("s") >= 0) nb = Math.max(itemSlotStartY + 1, bottom + dy)
                                                var nw = nr - nx
                                                var nh = nb - ny
                                                if (keepRatio && itemSlotStartW > 0 && itemSlotStartH > 0) {
                                                    var ratio = itemSlotStartW / itemSlotStartH
                                                    var horizontal = modelData.dir.indexOf("e") >= 0 || modelData.dir.indexOf("w") >= 0
                                                    var vertical = modelData.dir.indexOf("n") >= 0 || modelData.dir.indexOf("s") >= 0
                                                    if (horizontal && !vertical) {
                                                        nh = nw / ratio
                                                        nb = ny + nh
                                                    } else if (vertical && !horizontal) {
                                                        nw = nh * ratio
                                                        nr = nx + nw
                                                    } else {
                                                        if (Math.abs(nw - itemSlotStartW) / Math.max(itemSlotStartW, 1) >= Math.abs(nh - itemSlotStartH) / Math.max(itemSlotStartH, 1))
                                                            nh = nw / ratio
                                                        else
                                                            nw = nh * ratio
                                                        if (modelData.dir.indexOf("w") >= 0) nx = right - nw
                                                        else nr = itemSlotStartX + nw
                                                        if (modelData.dir.indexOf("n") >= 0) ny = bottom - nh
                                                        else nb = itemSlotStartY + nh
                                                    }
                                                }
                                                return {"x":nx,"y":ny,"width":Math.max(1,nw),"height":Math.max(1,nh)}
                                            }
''',
    "preserve-shift-ratio-preview",
)

text = text.replace(
    'window.queueItemSlotPreview(itemSlotResizedBounds(point.x, point.y), false)',
    'window.queueItemSlotPreview(itemSlotResizedBounds(point.x, point.y, (mouse.modifiers & Qt.ShiftModifier) !== 0), false)',
)
text = text.replace(
    'window.commitItemSlotPreview(itemSlotResizedBounds(point.x, point.y), "resize")',
    'window.commitItemSlotPreview(itemSlotResizedBounds(point.x, point.y, (mouse.modifiers & Qt.ShiftModifier) !== 0), "resize")',
)

TARGET.write_text(text, encoding="utf-8")
print(f"refined {TARGET}")
