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
    border.color: "#CBD5E1"

    property var scene: ({})
    property bool expanded: false

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
                text: expanded ? "Use ← → para reorganizar sem alterar o conteúdo" : "Reordenar"
                color: "#64748B"
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
            model: scene.pages || []
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: pageCard
                required property var modelData
                width: 166
                height: 62
                radius: 6
                color: modelData.id === scene.active_page_id ? "#EFF6FF" : "#FFFFFF"
                border.width: modelData.id === scene.active_page_id ? 2 : 1
                border.color: modelData.id === scene.active_page_id ? "#0F5BD8" : "#D9E2EF"

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 5
                    spacing: 4

                    ToolButton {
                        text: "←"
                        enabled: index > 0
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
                                text: modelData.id === scene.active_page_id ? "Página atual" : "Clique para abrir"
                                color: modelData.id === scene.active_page_id ? "#0F5BD8" : "#94A3B8"
                                font.pixelSize: 8
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: sceneBridge.dispatch(JSON.stringify({"name": "select_page", "page_id": modelData.id}))
                        }
                    }

                    ToolButton {
                        text: "→"
                        enabled: index < pageCount() - 1
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
}
