import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    property var theme
    property string title: ""
    default property alias contentData: body.data

    Layout.fillWidth: true
    implicitHeight: sectionLayout.implicitHeight + 24
    radius: theme ? theme.radius : 9
    color: theme ? theme.surface : "#FFFFFF"
    border.width: 1
    border.color: theme ? theme.border : "#DDE5F0"

    ColumnLayout {
        id: sectionLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        spacing: 9

        Label {
            Layout.fillWidth: true
            text: root.title.toUpperCase()
            color: theme ? theme.primary : "#5B45F6"
            font.pixelSize: theme ? theme.fontTiny : 9
            font.bold: true
            font.letterSpacing: 0.4
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            spacing: 8
        }
    }
}
