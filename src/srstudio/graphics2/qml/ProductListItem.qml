import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    required property var productData
    property var theme
    property bool active: false
    property bool canBind: false
    property string imageSource: ""
    signal bindRequested(var product)
    signal dragStarted(var sourceItem, real mouseX, real mouseY, var product)
    signal dragUpdated(var sourceItem, real mouseX, real mouseY, var product)
    signal dragFinished(var sourceItem, real mouseX, real mouseY, var product)
    signal dragCanceled()

    height: theme ? theme.productItemHeight : 66
    radius: theme ? theme.radius : 9
    color: active ? "#F3F0FF" : (pointer.containsMouse ? "#F6F8FD" : (theme ? theme.cardOnDark : "#FFFFFF"))
    border.width: pointer.dragging || active ? 2 : 1
    border.color: pointer.dragging ? (theme ? theme.primary : "#5B45F6") : (active ? "#8C78FF" : "#DFE6F1")

    function displayName() {
        return String(productData.display_name || productData.name || productData.original_name || "Produto")
    }

    function priceText() {
        var value = productData.price
        if (value === undefined || value === null || value === "")
            return "—"
        var raw = String(value).replace(".", ",")
        return raw.indexOf("R$") === 0 ? raw : "R$ " + raw
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 6
        anchors.bottomMargin: 6
        spacing: 8

        Rectangle {
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            radius: 4
            color: root.active ? (theme ? theme.primary : "#5B45F6") : "transparent"
            border.width: 1
            border.color: root.active ? (theme ? theme.primary : "#5B45F6") : "#A8B5CB"
            Text {
                anchors.centerIn: parent
                visible: root.active
                text: "✓"
                color: "white"
                font.pixelSize: 10
                font.bold: true
            }
        }

        Rectangle {
            Layout.preferredWidth: 48
            Layout.preferredHeight: 48
            radius: 7
            color: "#FFFFFF"
            border.width: 1
            border.color: "#E3E9F2"
            clip: true
            Image {
                anchors.fill: parent
                anchors.margins: 3
                source: root.imageSource
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: true
                smooth: true
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 1

            Label {
                Layout.fillWidth: true
                text: root.displayName()
                color: theme ? theme.text : "#172033"
                font.pixelSize: theme ? theme.fontBody : 11
                font.bold: true
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 4
                Rectangle {
                    visible: !!root.productData.category
                    implicitWidth: categoryText.implicitWidth + 10
                    implicitHeight: 17
                    radius: 5
                    color: "#EDF2F8"
                    Label { id: categoryText; anchors.centerIn: parent; text: String(root.productData.category || ""); color: "#64728B"; font.pixelSize: 8 }
                }
                Rectangle {
                    implicitWidth: unitText.implicitWidth + 10
                    implicitHeight: 17
                    radius: 5
                    color: "#EDF2F8"
                    Label { id: unitText; anchors.centerIn: parent; text: String(root.productData.unit || "UN"); color: "#64728B"; font.pixelSize: 8 }
                }
                Item { Layout.fillWidth: true }
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 76
            Layout.fillHeight: true
            spacing: 1
            Label {
                Layout.fillWidth: true
                text: root.priceText()
                color: theme ? theme.text : "#172033"
                horizontalAlignment: Text.AlignRight
                font.pixelSize: 12
                font.bold: true
            }
            Rectangle {
                visible: !!(root.productData.club || root.productData.club_price || root.productData.promotion || root.productData.promotional_price)
                Layout.alignment: Qt.AlignRight
                implicitWidth: badgeText.implicitWidth + 8
                implicitHeight: 16
                radius: 4
                color: root.productData.club || root.productData.club_price ? "#FFE45D" : "#FFD8DE"
                Label {
                    id: badgeText
                    anchors.centerIn: parent
                    text: root.productData.club || root.productData.club_price ? "Clube SR" : "Promoção"
                    color: "#473D12"
                    font.pixelSize: 8
                    font.bold: true
                }
            }
        }
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        preventStealing: dragging
        cursorShape: dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        property real pressX: 0
        property real pressY: 0
        property bool dragging: false

        onPressed: {
            pressX = mouse.x
            pressY = mouse.y
            dragging = false
        }
        onPositionChanged: {
            if (!pressed)
                return
            var dx = mouse.x - pressX
            var dy = mouse.y - pressY
            if (!dragging && Math.sqrt(dx * dx + dy * dy) >= 8) {
                dragging = true
                root.dragStarted(pointer, mouse.x, mouse.y, root.productData)
            }
            if (dragging)
                root.dragUpdated(pointer, mouse.x, mouse.y, root.productData)
        }
        onReleased: {
            if (dragging)
                root.dragFinished(pointer, mouse.x, mouse.y, root.productData)
            else
                root.dragCanceled()
            dragging = false
        }
        onCanceled: {
            dragging = false
            root.dragCanceled()
        }
        onDoubleClicked: if (root.canBind) root.bindRequested(root.productData)
    }
}
