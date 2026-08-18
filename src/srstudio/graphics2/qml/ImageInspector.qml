import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Rectangle {
    id: panel
    width: 336
    height: 650
    anchors.right: parent ? parent.right : undefined
    anchors.bottom: parent ? parent.bottom : undefined
    anchors.rightMargin: 8
    anchors.bottomMargin: 70
    z: 900000
    radius: 9
    color: "#FFFFFFF8"
    border.width: 1
    border.color: "#CBD5E1"
    visible: hasImageSelection

    property var scene: ({})
    property var imageNode: null
    property bool hasImageSelection: false
    readonly property bool bridgeHasImageSelection: {
        try {
            var parsedScene = JSON.parse(sceneBridge.sceneJson)
            return selectedImage(parsedScene) !== null
        } catch (error) {
            return false
        }
    }
    property bool syncing: false

    function activePage(sourceScene) {
        var currentScene = sourceScene || scene
        if (!currentScene.pages || !currentScene.pages.length)
            return null
        for (var i = 0; i < currentScene.pages.length; ++i)
            if (currentScene.pages[i].id === currentScene.active_page_id)
                return currentScene.pages[i]
        return currentScene.pages[0]
    }

    function selectedImage(sourceScene) {
        var currentScene = sourceScene || scene
        var page = activePage(currentScene)
        if (!page || !currentScene.editor)
            return null
        var id = String(currentScene.editor.anchor_id || "")
        var node = id && page.nodes ? page.nodes[id] : null
        if (!node && currentScene.editor.selection && currentScene.editor.selection.length)
            node = page.nodes[String(currentScene.editor.selection[0])] || null
        if (!node && page.nodes) {
            for (var nodeId in page.nodes) {
                if (page.nodes[nodeId] && page.nodes[nodeId].selected) {
                    node = page.nodes[nodeId]
                    break
                }
            }
        }
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
        return localSource(metadata.graphics2_preview_original_source || metadata.bound_image_source || metadata.source_url || assetSource)
    }

    function styleValue(key, fallbackValue) {
        if (!imageNode || !imageNode.style || imageNode.style[key] === undefined || imageNode.style[key] === null)
            return fallbackValue
        return imageNode.style[key]
    }

    function cropValue(shortKey, longKey) {
        var crop = styleValue("crop", ({})) || ({})
        var raw = crop[shortKey]
        if (raw === undefined || raw === null)
            raw = crop[longKey]
        return Math.max(0, Math.min(0.98, Number(raw || 0)))
    }

    function refresh() {
        syncing = true
        try {
            var parsedScene = JSON.parse(sceneBridge.sceneJson)
            var selected = selectedImage(parsedScene)
            scene = parsedScene
            imageNode = selected
            hasImageSelection = selected !== null && selected !== undefined
            if (!hasImageSelection)
                return
            var fit = String(styleValue("fit", "contain"))
            fitCombo.currentIndex = fit === "cover" ? 1 : fit === "fill" ? 2 : 0
            zoomSlider.value = Math.max(0.05, Number(styleValue("zoom", 1.0)))
            focusXSlider.value = Math.max(0, Math.min(1, Number(styleValue("focus_x", 0.5))))
            focusYSlider.value = Math.max(0, Math.min(1, Number(styleValue("focus_y", 0.5))))
            cropLeftSlider.value = cropValue("l", "left")
            cropTopSlider.value = cropValue("t", "top")
            cropRightSlider.value = cropValue("r", "right")
            cropBottomSlider.value = cropValue("b", "bottom")
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

    function applyFraming() {
        if (syncing || !imageNode)
            return
        cropCommand({
            "zoom": zoomSlider.value,
            "focus_x": focusXSlider.value,
            "focus_y": focusYSlider.value
        })
    }

    function applyCrop(edge, value) {
        if (syncing || !imageNode)
            return
        var command = ({})
        command["crop_" + edge] = value
        cropCommand(command)
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { panel.refresh() }
    }

    Component.onCompleted: refresh()

    FileDialog {
        id: replaceImageDialog
        title: "Selecionar nova imagem"
        fileMode: FileDialog.OpenFile
        nameFilters: [
            "Imagens (*.png *.jpg *.jpeg *.jfif *.webp *.bmp *.gif *.tif *.tiff)",
            "Todos os arquivos (*)"
        ]
        onAccepted: {
            if (!imageNode)
                return
            sceneBridge.dispatch(JSON.stringify({
                "name": "replace_image",
                "node_id": imageNode.id,
                "source": selectedFile.toString()
            }))
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 5
        radius: 7
        color: "transparent"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Ajuste de imagem"; color: "#111827"; font.bold: true; font.pixelSize: 15 }
                Item { Layout.fillWidth: true }
                Label { text: imageNode ? (imageNode.name || "Imagem") : ""; color: "#64748B"; font.pixelSize: 9; elide: Text.ElideRight; Layout.maximumWidth: 135 }
            }

            Rectangle {
                id: previewFrame
                Layout.fillWidth: true
                Layout.preferredHeight: 160
                radius: 6
                color: "#F1F5F9"
                border.color: "#CBD5E1"
                clip: true

                SceneImage {
                    id: previewImage
                    anchors.fill: parent
                    sourceUrl: imageSource(imageNode)
                    fit: fitCombo.currentIndex === 1 ? "cover" : fitCombo.currentIndex === 2 ? "fill" : "contain"
                    imageZoom: zoomSlider.value
                    focusX: focusXSlider.value
                    focusY: focusYSlider.value
                    cropLeft: cropLeftSlider.value
                    cropTop: cropTopSlider.value
                    cropRight: cropRightSlider.value
                    cropBottom: cropBottomSlider.value
                    flipX: imageNode ? !!styleValue("flip_x", false) : false
                    flipY: imageNode ? !!styleValue("flip_y", false) : false
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

            Button {
                Layout.fillWidth: true
                text: "Substituir imagem…"
                onClicked: if (imageNode) replaceImageDialog.open()
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Encaixe"; color: "#475569"; font.bold: true; Layout.preferredWidth: 56 }
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
                Label { text: "Zoom"; color: "#475569"; font.bold: true; Layout.preferredWidth: 56 }
                Slider {
                    id: zoomSlider
                    Layout.fillWidth: true
                    from: 0.5
                    to: 5.0
                    value: 1.0
                    stepSize: 0.01
                    onPressedChanged: if (!pressed) applyFraming()
                }
                Label { text: zoomSlider.value.toFixed(2) + "×"; color: "#64748B"; Layout.preferredWidth: 42 }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Foco X"; color: "#475569"; font.bold: true; Layout.preferredWidth: 56 }
                Slider {
                    id: focusXSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    value: 0.5
                    stepSize: 0.01
                    onPressedChanged: if (!pressed) applyFraming()
                }
                Label { text: Math.round(focusXSlider.value * 100) + "%"; color: "#64748B"; Layout.preferredWidth: 42 }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Foco Y"; color: "#475569"; font.bold: true; Layout.preferredWidth: 56 }
                Slider {
                    id: focusYSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    value: 0.5
                    stepSize: 0.01
                    onPressedChanged: if (!pressed) applyFraming()
                }
                Label { text: Math.round(focusYSlider.value * 100) + "%"; color: "#64748B"; Layout.preferredWidth: 42 }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#E2E8F0" }
            Label { text: "Corte da imagem-fonte"; color: "#334155"; font.bold: true; font.pixelSize: 10 }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Esq."; color: "#475569"; Layout.preferredWidth: 56 }
                Slider {
                    id: cropLeftSlider
                    Layout.fillWidth: true
                    from: 0
                    to: Math.min(0.98, Math.max(0, 0.995 - cropRightSlider.value))
                    value: 0
                    stepSize: 0.005
                    onPressedChanged: if (!pressed) applyCrop("left", value)
                }
                Label { text: (cropLeftSlider.value * 100).toFixed(1) + "%"; color: "#64748B"; Layout.preferredWidth: 46 }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Topo"; color: "#475569"; Layout.preferredWidth: 56 }
                Slider {
                    id: cropTopSlider
                    Layout.fillWidth: true
                    from: 0
                    to: Math.min(0.98, Math.max(0, 0.995 - cropBottomSlider.value))
                    value: 0
                    stepSize: 0.005
                    onPressedChanged: if (!pressed) applyCrop("top", value)
                }
                Label { text: (cropTopSlider.value * 100).toFixed(1) + "%"; color: "#64748B"; Layout.preferredWidth: 46 }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Dir."; color: "#475569"; Layout.preferredWidth: 56 }
                Slider {
                    id: cropRightSlider
                    Layout.fillWidth: true
                    from: 0
                    to: Math.min(0.98, Math.max(0, 0.995 - cropLeftSlider.value))
                    value: 0
                    stepSize: 0.005
                    onPressedChanged: if (!pressed) applyCrop("right", value)
                }
                Label { text: (cropRightSlider.value * 100).toFixed(1) + "%"; color: "#64748B"; Layout.preferredWidth: 46 }
            }

            RowLayout {
                Layout.fillWidth: true
                Label { text: "Base"; color: "#475569"; Layout.preferredWidth: 56 }
                Slider {
                    id: cropBottomSlider
                    Layout.fillWidth: true
                    from: 0
                    to: Math.min(0.98, Math.max(0, 0.995 - cropTopSlider.value))
                    value: 0
                    stepSize: 0.005
                    onPressedChanged: if (!pressed) applyCrop("bottom", value)
                }
                Label { text: (cropBottomSlider.value * 100).toFixed(1) + "%"; color: "#64748B"; Layout.preferredWidth: 46 }
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
                    onClicked: if (imageNode) cropCommand({
                        "fit": "contain",
                        "zoom": 1.0,
                        "focus_x": 0.5,
                        "focus_y": 0.5,
                        "flip_x": false,
                        "flip_y": false,
                        "crop_reset": true
                    })
                }
            }

            Label {
                Layout.fillWidth: true
                text: "A substituição preserva posição, tamanho, crop, rotação e camadas. Crop, foco, zoom e espelhamento são persistidos no SR Scene e usados pelo canvas e pela exportação."
                wrapMode: Text.WordWrap
                color: "#64748B"
                font.pixelSize: 9
            }
        }
    }
}
