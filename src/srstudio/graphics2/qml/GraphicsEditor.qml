import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: window
    width: 1600; height: 960; minimumWidth: 1100; minimumHeight: 700
    visible: true; title: "SR Graphics Engine 2.0"
    property var scene: JSON.parse(sceneBridge.sceneJson)
    property var page: scene.pages && scene.pages.length ? scene.pages.find(function(p) { return p.id === scene.active_page_id }) || scene.pages[0] : null
    property real zoom: 0.72

    Connections {
        target: sceneBridge
        function onSceneChanged() {
            window.scene = JSON.parse(sceneBridge.sceneJson)
            window.page = window.scene.pages.find(function(p) { return p.id === window.scene.active_page_id }) || window.scene.pages[0]
        }
    }
    Shortcut { sequence: StandardKey.Undo; onActivated: sceneBridge.undo() }
    Shortcut { sequence: StandardKey.Redo; onActivated: sceneBridge.redo() }
    Shortcut { sequence: StandardKey.Delete; onActivated: sceneBridge.dispatch('{"name":"delete"}') }
    Shortcut { sequence: "Ctrl+D"; onActivated: sceneBridge.dispatch('{"name":"duplicate"}') }

    header: ToolBar {
        RowLayout { anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
            Label { text: "SR Graphics Engine 2.0"; font.bold: true; font.pixelSize: 16 }
            ToolSeparator {}
            ToolButton { text: "↶"; onClicked: sceneBridge.undo() }
            ToolButton { text: "↷"; onClicked: sceneBridge.redo() }
            ToolSeparator {}
            ToolButton { text: "Frente"; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"front"}') }
            ToolButton { text: "Fundo"; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"back"}') }
            ToolButton { text: "Duplicar"; onClicked: sceneBridge.dispatch('{"name":"duplicate"}') }
            Item { Layout.fillWidth: true }
            Label { text: Math.round(window.zoom * 100) + "%" }
            Slider { from: 0.15; to: 2.5; value: window.zoom; Layout.preferredWidth: 180; onMoved: window.zoom = value }
        }
    }

    SplitView { anchors.fill: parent
        Rectangle { SplitView.preferredWidth: 270; color: "#f8fafc"; border.color: "#dbe3ef"
            ColumnLayout { anchors.fill: parent; anchors.margins: 12
                Label { text: "Produtos / Elementos"; font.bold: true; font.pixelSize: 17 }
                Label { text: "SR Scene 2: geometria independente do zoom e do DOM."; color: "#64748b"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                ListView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    model: page ? Object.values(page.nodes).sort(function(a,b) { return a.z_index - b.z_index }) : []
                    delegate: ItemDelegate { width: ListView.view.width; text: modelData.name || modelData.kind; onClicked: sceneBridge.selectNode(modelData.id) }
                }
            }
        }
        Rectangle { id: workspace; SplitView.fillWidth: true; SplitView.fillHeight: true; color: "#dce4ef"
            Flickable { anchors.fill: parent; contentWidth: Math.max(width, (page ? page.width : 1080) * zoom + 220); contentHeight: Math.max(height, (page ? page.height : 1350) * zoom + 220); clip: true
                Rectangle { id: sheet; x: 110; y: 90; width: (page ? page.width : 1080) * zoom; height: (page ? page.height : 1350) * zoom; color: page ? page.background : "white"; border.color: "#c7d2e0"
                    Repeater { model: page ? Object.values(page.nodes).filter(function(n) { return n.visible }).sort(function(a,b) { return a.z_index - b.z_index }) : []
                        delegate: Item { id: nodeItem; required property var modelData
                            x: modelData.transform.x * zoom; y: modelData.transform.y * zoom; width: Math.max(1, modelData.transform.width * zoom); height: Math.max(1, modelData.transform.height * zoom); rotation: modelData.transform.rotation; opacity: modelData.opacity
                            Rectangle { anchors.fill: parent; visible: modelData.kind === "rect" || modelData.kind === "group"; color: modelData.kind === "group" ? "transparent" : (modelData.style.fill || "transparent"); border.width: modelData.kind === "group" ? 1 : Number(modelData.style.stroke_width || 0); border.color: modelData.kind === "group" ? "#2563eb66" : (modelData.style.stroke || "transparent"); radius: Number(modelData.style.radius || 0) * zoom }
                            Text { anchors.fill: parent; visible: modelData.kind === "text"; text: modelData.text || ""; color: modelData.style.color || "#111827"; font.family: modelData.style.font_family || "Segoe UI"; font.pixelSize: Math.max(6, Number(modelData.style.font_size || 20) * zoom); font.bold: Number(modelData.style.font_weight || 400) >= 700; horizontalAlignment: modelData.style.align === "left" ? Text.AlignLeft : modelData.style.align === "right" ? Text.AlignRight : Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; wrapMode: modelData.style.nowrap ? Text.NoWrap : Text.WordWrap; elide: Text.ElideRight }
                            Image { anchors.fill: parent; visible: modelData.kind === "image" || modelData.kind === "background"; source: modelData.metadata.bound_image_source || modelData.metadata.source_url || ""; fillMode: modelData.style.fit === "cover" ? Image.PreserveAspectCrop : modelData.style.fit === "fill" ? Image.Stretch : Image.PreserveAspectFit; asynchronous: true; cache: true }
                            MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton; drag.target: parent; enabled: !modelData.locked
                                onPressed: sceneBridge.selectNode(modelData.id)
                                onReleased: { var dx = (parent.x / zoom) - modelData.transform.x; var dy = (parent.y / zoom) - modelData.transform.y; if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001) sceneBridge.moveSelection(dx, dy) }
                            }
                        }
                    }
                }
            }
        }
        Rectangle { SplitView.preferredWidth: 300; color: "#ffffff"; border.color: "#dbe3ef"
            ColumnLayout { anchors.fill: parent; anchors.margins: 14
                Label { text: "Propriedades"; font.bold: true; font.pixelSize: 17 }
                Label { text: sceneBridge.status; color: "#64748b"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                ToolSeparator { Layout.fillWidth: true }
                Button { text: "Bloquear"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"lock","value":true}') }
                Button { text: "Desbloquear"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"lock","value":false}') }
                Button { text: "Ocultar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"hide","value":true}') }
                Button { text: "Alinhar à esquerda"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"left"}') }
                Button { text: "Centralizar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"center"}') }
                Button { text: "Distribuir horizontal"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"distribute","axis":"horizontal"}') }
                Item { Layout.fillHeight: true }
                Label { text: "Qt Quick / RHI • interface GPU"; color: "#2563eb"; font.bold: true }
            }
        }
    }
}
