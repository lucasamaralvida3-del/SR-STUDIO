import QtQuick
import QtQuick.Controls

Button {
    id: root
    property var theme
    property bool active: false

    implicitHeight: theme ? theme.controlSmall : 28
    leftPadding: 10
    rightPadding: 10
    topPadding: 0
    bottomPadding: 0

    contentItem: Text {
        text: root.text
        color: root.active ? "#FFFFFF" : (theme ? theme.navMuted : "#B7C2E0")
        font.pixelSize: theme ? theme.fontSmall : 10
        font.bold: root.active
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: theme ? theme.radiusPill : 999
        color: root.active ? (theme ? theme.primary : "#5B45F6") : (root.hovered ? "#FFFFFF16" : "#FFFFFF0B")
        border.width: root.active ? 0 : 1
        border.color: "#FFFFFF14"
    }
}
