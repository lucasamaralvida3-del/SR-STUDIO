import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    width: Math.max(320, Math.min(parent ? parent.width - 700 : 720, 760))
    height: expanded ? 112 : 38
    anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
    anchors.bottom: parent ? parent.bottom : undefined
    anchors.bottomMargin: 66
    z: 898000
    radius: 9
    color: "#FFFFFFF7"
    border.width: 1
    border.color: pageDragActive ? "#0F5BD8" : "#CBD5E1"

    property var scene: ({})
    property bool expanded: false
    property bool pageDragActive: false
    property string draggedPageId: ""
    property string draggedPageName: ""
    property int dragTargetIndex: -1
    property real dragGhostX: 0

    function refresh() {
        try {
            scene = JSON.parse(sceneBridge.sceneJson)
        } catch (error) {
            scene = ({})
        }
    }

    function pageCount() {
        return scene.pages ? scene.pages.length : 0
    }

    function movePage(pageId, mode) {
        sceneBridge.dispatch(JSON.stringify({"name": "reorder_page", "page_id": pageId, "mode": mode}))
    }

    function beginPageDrag(sourceItem, mouseX, pageData) {
        pageDragActive = true
        draggedPageId = String(pageData.id || "")
        draggedPageName = String(pageData.name || "Página")
        updatePageDrag(sourceItem, mouseX)
    }

    function updatePageDrag(sourceItem, mouseX) {
        if (!pageDragActive || !sourceItem)
            return
        var local = sourceItem.mapToItem(pageStrip, mouseX, 0)
        dragGhostX = Math.max(0, Math.min(pageStrip.width, local.x))
        var contentPoint = sourceItem.mapToItem(pageStrip.contentItem, mouseX, pageStrip.height / 2)
        var target = pageStrip.indexAt(contentPoint.x, contentPoint.y)
        if (target < 0 && pageCount() > 0) {
            var approximate = Math.floor((contentPoint.x + pageStrip.spacing / 2) / (166 + pageStrip.spacing))
            target = Math.max(0, Math.min(pageCount() - 1, approximate))
        }
        dragTargetIndex = target
    }

    function finishPageDrag() {
        if (pageDragActive && draggedPageId && dragTargetIndex >= 0) {
            sceneBridge.dispatch(JSON.stringify({
                "name": "reorder_page",
                "page_id": draggedPageId,
                "target_index": dragTargetIndex
            }))
        }
        cancelPageDrag()
    }

    function cancelPageDrag() {
        pageDragActive = false
        draggedPageId = ""
        draggedPageName = ""
        dragTargetIndex = -1
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { panel.refresh() }
    }

    Component.onCompleted: refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 5

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: "Ordem das páginas"
                color: "#334155"
                font.bold: true
                font.pixelSize: 10
            }
            Label {
                text: pageCount() + (pageCount() === 1 ? " página" : " páginas")
                color: "#94A3B8"
                font.pixelSize: 9
            }
            Item { Layout.fillWidth: true }
            Label {
                text: pageDragActive
                    ? (dragTargetIndex >= 0 ? "Soltar na posição " + (dragTargetIndex + 1) : "Arraste para a posição")
                    : (expanded ? "Arraste ou use ← →" : "Reordenar")
                color: pageDragActive ? "#0F5BD8" : "#64748B"
                font.bold: pageDragActive
                font.pixelSize: 9
            }
            ToolButton {
                text: expanded ? "▾" : "▴"
                implicitWidth: 28
                implicitHeight: 26
                onClicked: expanded = !expanded
            }
        }

        ListView {
            id: pageStrip
            visible: expanded
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: ListView.Horizontal
            spacing: 7
            clip: true
            interactive: !pageDragActive
            model: scene.pages || []
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: pageCard
                required property var modelData
                width: 166
                height: 62
                radius: 6
                opacity: pageDragActive && draggedPageId === String(modelData.id) ? 0.45 : 1.0
                color: dragTargetIndex === index && pageDragActive
                    ? "#DBEAFE"
                    : (modelData.id === scene.active_page_id ? "#EFF6FF" : "#FFFFFF")
                border.width: dragTargetIndex === index && pageDragActive ? 2 : (modelData.id === scene.active_page_id ? 2 : 1)
                border.color: dragTargetIndex === index && pageDragActive
                    ? "#2563EB"
                    : (modelData.id === scene.active_page_id ? "#0F5BD8" : "#D9E2EF")

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 5
                    spacing: 4

                    ToolButton {
                        text: "←"
                        enabled: !pageDragActive && index > 0
                        implicitWidth: 25
                        implicitHeight: 28
                        ToolTip.text: "Mover página para a esquerda"
                        ToolTip.visible: hovered
                        onClicked: movePage(modelData.id, "previous")
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Column {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Label {
                                width: parent.width
                                text: (index + 1) + " · " + (modelData.name || "Página")
                                color: "#111827"
                                font.bold: true
                                font.pixelSize: 9
                                elide: Text.ElideRight
                            }
                            Label {
                                width: parent.width
                                text: pageDragActive && dragTargetIndex === index
                                    ? "Soltar aqui"
                                    : (modelData.id === scene.active_page_id ? "Página atual" : "Clique ou arraste")
                                color: pageDragActive && dragTargetIndex === index
                                    ? "#1D4ED8"
                                    : (modelData.id === scene.active_page_id ? "#0F5BD8" : "#94A3B8")
                                font.bold: pageDragActive && dragTargetIndex === index
                                font.pixelSize: 8
                            }
                        }

                        MouseArea {
                            id: dragArea
                            anchors.fill: parent
                            cursorShape: pageDragActive ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                            preventStealing: true
                            property real pressX: 0
                            property bool dragging: false
                            onPressed: {
                                pressX = mouse.x
                                dragging = false
                            }
                            onPositionChanged: {
                                if (!pressed)
                                    return
                                if (!dragging && Math.abs(mouse.x - pressX) >= 7) {
                                    dragging = true
                                    beginPageDrag(dragArea, mouse.x, pageCard.modelData)
                                }
                                if (dragging)
                                    updatePageDrag(dragArea, mouse.x)
                            }
                            onReleased: {
                                if (dragging)
                                    finishPageDrag()
                                else
                                    sceneBridge.dispatch(JSON.stringify({"name": "select_page", "page_id": modelData.id}))
                                dragging = false
                            }
                            onCanceled: {
                                dragging = false
                                cancelPageDrag()
                            }
                        }
                    }

                    ToolButton {
                        text: "→"
                        enabled: !pageDragActive && index < pageCount() - 1
                        implicitWidth: 25
                        implicitHeight: 28
                        ToolTip.text: "Mover página para a direita"
                        ToolTip.visible: hovered
                        onClicked: movePage(modelData.id, "next")
                    }
                }
            }
        }
    }

    Rectangle {
        visible: pageDragActive
        x: Math.max(8, Math.min(panel.width - width - 8, dragGhostX - width / 2))
        y: 38
        width: 170
        height: 34
        z: 20
        radius: 6
        color: "#F8FBFFEE"
        border.width: 2
        border.color: "#0F5BD8"
        opacity: 0.95

        RowLayout {
            anchors.fill: parent
            anchors.margins: 6
            spacing: 5
            Label { text: "↔"; color: "#0F5BD8"; font.bold: true }
            Label {
                Layout.fillWidth: true
                text: draggedPageName || "Página"
                color: "#111827"
                font.bold: true
                font.pixelSize: 9
                elide: Text.ElideRight
            }
            Label {
                text: dragTargetIndex >= 0 ? String(dragTargetIndex + 1) : "—"
                color: "#0F5BD8"
                font.bold: true
            }
        }
    }
}
