import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    width: 326
    height: 430
    anchors.right: parent ? parent.right : undefined
    anchors.bottom: parent ? parent.bottom : undefined
    anchors.rightMargin: 8
    anchors.bottomMargin: 70
    z: 900000
    radius: 9
    color: "#FFFFFFF8"
    border.width: 1
    border.color: "#CBD5E1"
    visible: !!imageNode

    property var scene: ({})
    property var imageNode: null
    property bool syncing: false

    function activePage() {
        if (!scene.pages || !scene.pages.length)
            return null
        for (var i = 0; i < scene.pages.length; ++i)
            if (scene.pages[i].id === scene.active_page_id)
                return scene.pages[i]
        return scene.pages[0]
    }

    function selectedImage() {
        var page = activePage()
        if (!page || !scene.editor)
            return null
        var id = String(scene.editor.anchor_id || "")
        var node = id && page.nodes ? page.nodes[id] : null
        if (!node && scene.editor.selection && scene.editor.selection.length)
            node = page.nodes[String(scene.editor.selection[0])] || null
        return node && (node.kind === "image" || node.kind === "background") ? node : null
    }

    function localSource(value) {
        var text = String(value || "")
        if (!text)
            return ""
        if (/^[A-Za-z]:[\\/]/.test(text))
            return "file:///" + text.replace(/\\/g, "/")
        return text
    }

    function imageSource(node) {
        if (!node)
            return ""
        var metadata = node.metadata || {}
        var assetSource = ""
        if (node.asset_id && scene.assets && scene.assets[node.asset_id])
            assetSource = scene.assets[node.asset_id].source || ""
        return localSource(metadata.bound_image_source || metadata.source_url || assetSource)
    }

    function styleValue(key, fallbackValue) {
        if (!imageNode || !imageNode.style || imageNode.style[key] === undefined || imageNode.style[key] === null)
            return fallbackValue
        return imageNode.style[key]
    }

    function refresh() {
        syncing = true
        try {
            scene = JSON.parse(sceneBridge.sceneJson)
            imageNode = selectedImage()
            if (!imageNode)
                return
            var fit = String(styleValue("fit", "contain"))
            fitCombo.currentIndex = fit === "cover" ? 1 : fit === "fill" ? 2 : 0
            zoomSlider.value = Math.max(0.05, Number(styleValue("zoom", 1.0)))
            focusXSlider.value = Math.max(0, Math.min(1, Number(styleValue("focus_x", 0.5))))
            focusYSlider.value = Math.max(0, Math.min(1, Number(styleValue("focus_y", 0.5))))
        } finally {
            syncing = false
        }
    }

    function cropCommand(extra) {
        if (!imageNode)
            return
        var command = {"name": "crop", "node_id": imageNode.id}
        for (var key in extra)
            command[key] = extra[key]
        sceneBridge.dispatch(JSON.stringify(command))
    }

    function applySliders() {
        if (syncing || !imageNode)
            return
        cropCommand({
            "zoom": zoomSlider.value,
            "focus_x": focusXSlider.value,
            "focus_y": focusYSlider.value
        })
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { panel.refresh() }
    }

    Component.onCompleted: refresh()

    Rectangle {
        anchors.fill: parent
        anchors.margins: 5
        radius: 7
        color: "transparent"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 7

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Ajuste de imagem"; color: "#111827"; font.bold: true; font.pixelSize: 15 }
                Item { Layout.fillWidth: true }
                Label { text: imageNode ? (imageNode.name || "Imagem") : ""; color: "#64748B"; font.pixelSize: 9; elide: Text.ElideRight; Layout.maximumWidth: 135 }
            }

            Rectangle {
                id: previewFrame
                Layout.fillWidth: true
                Layout.preferredHeight: 178
                radius: 6
                color: "#F1F5F9"
                border.color: "#CBD5E1"
                clip: true

                Image {
                    id: previewImage
                    property real iw: Math.max(1, Number(sourceSize.width || implicitWidth || 1))
                    property real ih: Math.max(1, Number(sourceSize.height || implicitHeight || 1))
                    property string fit: imageNode ? String(styleValue("fit", "contain")) : "contain"
                    property real focusX: imageNode ? Math.max(0, Math.min(1, Number(styleValue("focus_x", 0.5)))) : 0.5
                    property real focusY: imageNode ? Math.max(0, Math.min(1, Number(styleValue("focus_y", 0.5)))) : 0.5
                    property real imageZoom: imageNode ? Math.max(0.05, Number(styleValue("zoom", 1.0))) : 1.0
                    property bool cropMode: fit === "cover" || imageZoom > 1.0001
                    property real baseScale: fit === "fill" ? 1 : (cropMode ? Math.max(previewFrame.width / iw, previewFrame.height / ih) : Math.min(previewFrame.width / iw, previewFrame.height / ih))
                    property real scaleValue: fit === "fill" ? 1 : baseScale * (cropMode ? imageZoom : 1)

                    source: imageSource(imageNode)
                    width: fit === "fill" ? previewFrame.width : iw * scaleValue
                    height: fit === "fill" ? previewFrame.height : ih * scaleValue
                    x: fit === "fill" ? 0 : (previewFrame.width - width) * focusX
                    y: fit === "fill" ? 0 : (previewFrame.height - height) * focusY
                    fillMode: Image.Stretch
                    mirror: imageNode ? !!styleValue("flip_x", false) : false
                    mirrorVertically: imageNode ? !!styleValue("flip_y", false) : false
                    asynchronous: true
                    cache: true
                    mipmap: true
                    smooth: true
                }

                Rectangle {
                    anchors.centerIn: parent
                    width: 18
                    height: 18
                    radius: 9
                    color: "transparent"
                    border.width: 1
                    border.color: "#FFFFFFCC"
                    visible: previewImage.status === Image.Ready
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Encaixe"; color: "#475569"; font.bold: true; Layout.preferredWidth: 54 }
                ComboBox {
                    id: fitCombo
                    Layout.fillWidth: true
                    model: ["Conter", "Cobrir", "Preencher"]
                    onActivated: {
                        if (syncing || !imageNode) return
                        cropCommand({"fit": currentIndex === 1 ? "cover" : currentIndex === 2 ? "fill" : "contain"})
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Zoom"; color: "#475569"; font.bold: true; Layout.preferredWidth: 54 }
                Slider {
                    id: zoomSlider
                    Layout.fillWidth: true
                    from: 0.5
                    to: 5.0
                    value: 1.0
                    stepSize: 0.01
                    onMoved: if (!syncing && imageNode) imageNode.style.zoom = value
                    onPressedChanged: if (!pressed) applySliders()
                }
                Label { text: zoomSlider.value.toFixed(2) + "×"; color: "#64748B"; Layout.preferredWidth: 40 }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Foco X"; color: "#475569"; font.bold: true; Layout.preferredWidth: 54 }
                Slider {
                    id: focusXSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    value: 0.5
                    stepSize: 0.01
                    onMoved: if (!syncing && imageNode) imageNode.style.focus_x = value
                    onPressedChanged: if (!pressed) applySliders()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Foco Y"; color: "#475569"; font.bold: true; Layout.preferredWidth: 54 }
                Slider {
                    id: focusYSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    value: 0.5
                    stepSize: 0.01
                    onMoved: if (!syncing && imageNode) imageNode.style.focus_y = value
                    onPressedChanged: if (!pressed) applySliders()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: "↔ Espelhar"
                    Layout.fillWidth: true
                    onClicked: if (imageNode) cropCommand({"flip_x": !Boolean(styleValue("flip_x", false))})
                }
                Button {
                    text: "↕ Inverter"
                    Layout.fillWidth: true
                    onClicked: if (imageNode) cropCommand({"flip_y": !Boolean(styleValue("flip_y", false))})
                }
                Button {
                    text: "Reset"
                    onClicked: if (imageNode) cropCommand({"fit": "contain", "zoom": 1.0, "focus_x": 0.5, "focus_y": 0.5, "flip_x": false, "flip_y": false})
                }
            }

            Label {
                Layout.fillWidth: true
                text: "O preview usa o mesmo contrato fit + zoom + foco do renderer de produção."
                wrapMode: Text.WordWrap
                color: "#64748B"
                font.pixelSize: 9
            }
        }
    }
}
