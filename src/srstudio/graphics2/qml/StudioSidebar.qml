import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property var theme
    property string currentSection: "Produtos"
    signal sectionRequested(string section)

    color: theme ? theme.navDeep : "#0A1236"
    implicitWidth: theme ? theme.sidebarWidth : 82

    readonly property var entries: [
        {"label":"Templates", "icon":"▣"},
        {"label":"Produtos", "icon":"◈"},
        {"label":"Uploads", "icon":"⇧"},
        {"label":"Texto", "icon":"T"},
        {"label":"Formas", "icon":"○"},
        {"label":"Imagens", "icon":"▧"},
        {"label":"Fundo", "icon":"▥"},
        {"label":"Dados", "icon":"◇"},
        {"label":"Estatísticas", "icon":"◫"},
        {"label":"Favoritos", "icon":"☆"}
    ]

    Rectangle {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 58
        color: "transparent"

        Column {
            anchors.centerIn: parent
            spacing: 1
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "▰"
                color: "#B9A8FF"
                font.pixelSize: 22
                font.bold: true
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "SR"
                color: theme ? theme.navText : "white"
                font.pixelSize: 10
                font.bold: true
            }
        }
    }

    Column {
        id: navColumn
        anchors.top: parent.top
        anchors.topMargin: 64
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 2

        Repeater {
            model: root.entries
            delegate: Item {
                id: entry
                required property var modelData
                width: navColumn.width
                height: 54
                property bool active: root.currentSection === modelData.label

                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: 5
                    anchors.rightMargin: 5
                    radius: theme ? theme.radiusSmall : 6
                    color: entry.active ? (theme ? theme.primary : "#5B45F6") : (navMouse.containsMouse ? "#FFFFFF10" : "transparent")
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 2
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: entry.modelData.icon
                        color: entry.active ? "#FFFFFF" : (theme ? theme.navMuted : "#B7C2E0")
                        font.pixelSize: 17
                        font.bold: entry.active
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: Math.max(58, entry.width - 10)
                        horizontalAlignment: Text.AlignHCenter
                        text: entry.modelData.label
                        color: entry.active ? "#FFFFFF" : (theme ? theme.navMuted : "#B7C2E0")
                        font.pixelSize: 8
                        font.bold: entry.active
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: navMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.sectionRequested(entry.modelData.label)
                }
            }
        }
    }

    Item {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 64

        Rectangle {
            anchors.fill: parent
            anchors.margins: 8
            radius: theme ? theme.radius : 9
            color: helpMouse.containsMouse ? "#FFFFFF16" : "#FFFFFF0B"
            border.width: 1
            border.color: "#FFFFFF12"
        }
        Column {
            anchors.centerIn: parent
            spacing: 2
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "?"; color: "#FFFFFF"; font.pixelSize: 16; font.bold: true }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Ajuda"; color: theme ? theme.navMuted : "#B7C2E0"; font.pixelSize: 8 }
        }
        MouseArea { id: helpMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor }
    }
}
