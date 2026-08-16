import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: window
    width: 1760
    height: 1020
    minimumWidth: 1180
    minimumHeight: 760
    visible: true
    title: "SR Graphics Engine 2.0"

    property var scene: JSON.parse(sceneBridge.sceneJson)
    property var page: activePage()
    property real zoom: 0.72
    property bool showGrid: true
    property bool showRulers: true
    property real gridStep: 50
    property string selectedSlotId: ""
    property var anchorNode: selectedNode()

    function activePage() {
        if (!scene.pages || !scene.pages.length)
            return null
        for (var i = 0; i < scene.pages.length; ++i)
            if (scene.pages[i].id === scene.active_page_id)
                return scene.pages[i]
        return scene.pages[0]
    }

    function nodes() {
        return page ? Object.values(page.nodes || {}) : []
    }

    function slots() {
        return page ? Object.values(page.slots || {}) : []
    }

    function products() {
        return scene.editor && scene.editor.products ? scene.editor.products : []
    }

    function selectedIds() {
        return scene.editor && scene.editor.selection ? scene.editor.selection : []
    }

    function selectedNode() {
        if (!page || !scene.editor)
            return null
        var id = scene.editor.anchor_id || ""
        if (id && page.nodes[id])
            return page.nodes[id]
        var selected = selectedIds()
        return selected.length && page.nodes[selected[0]] ? page.nodes[selected[0]] : null
    }

    function isSelected(node) {
        return selectedIds().indexOf(node.id) >= 0
    }

    function effectiveVisible(node) {
        if (!node || node.visible === false)
            return false
        var parentId = node.parent_id || ""
        var guard = 0
        while (parentId && page && page.nodes[parentId] && guard++ < 128) {
            if (page.nodes[parentId].visible === false)
                return false
            parentId = page.nodes[parentId].parent_id || ""
        }
        return true
    }

    function effectiveLocked(node) {
        if (!node)
            return true
        if (node.locked)
            return true
        var parentId = node.parent_id || ""
        var guard = 0
        while (parentId && page && page.nodes[parentId] && guard++ < 128) {
            if (page.nodes[parentId].locked)
                return true
            parentId = page.nodes[parentId].parent_id || ""
        }
        return false
    }

    function effectiveOpacity(node) {
        if (!node)
            return 0
        var value = Number(node.opacity === undefined ? 1 : node.opacity)
        var parentId = node.parent_id || ""
        var guard = 0
        while (parentId && page && page.nodes[parentId] && guard++ < 128) {
            value *= Number(page.nodes[parentId].opacity === undefined ? 1 : page.nodes[parentId].opacity)
            parentId = page.nodes[parentId].parent_id || ""
        }
        return Math.max(0, Math.min(1, value))
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
        return localSource((node.metadata || {}).bound_image_source || (node.metadata || {}).source_url || "")
    }

    function slotBounds(slot) {
        if (!page || !slot)
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        var ids = Object.values(slot.node_by_role || {})
        var minX = 1e18, minY = 1e18, maxX = -1e18, maxY = -1e18
        for (var i = 0; i < ids.length; ++i) {
            var node = page.nodes[ids[i]]
            if (!node)
                continue
            var t = node.transform
            minX = Math.min(minX, Number(t.x))
            minY = Math.min(minY, Number(t.y))
            maxX = Math.max(maxX, Number(t.x) + Number(t.width))
            maxY = Math.max(maxY, Number(t.y) + Number(t.height))
        }
        if (minX === 1e18)
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        return {"x": minX, "y": minY, "width": Math.max(1, maxX - minX), "height": Math.max(1, maxY - minY)}
    }

    function bindProduct(product) {
        if (!selectedSlotId) {
            sceneBridge.dispatch(JSON.stringify({"name": "clear_selection"}))
            return
        }
        sceneBridge.dispatch(JSON.stringify({"name": "bind_product", "slot_id": selectedSlotId, "product_id": product.id}))
    }

    function syncInspector() {
        var node = selectedNode()
        anchorNode = node
        if (!node) {
            inspectorName.text = "Nada selecionado"
            xField.text = ""
            yField.text = ""
            wField.text = ""
            hField.text = ""
            rotationField.text = ""
            opacityField.value = 1
            textEditor.text = ""
            return
        }
        inspectorName.text = node.name || node.kind || "Elemento"
        xField.text = Number(node.transform.x).toFixed(2)
        yField.text = Number(node.transform.y).toFixed(2)
        wField.text = Number(node.transform.width).toFixed(2)
        hField.text = Number(node.transform.height).toFixed(2)
        rotationField.text = Number(node.transform.rotation || 0).toFixed(2)
        opacityField.value = Number(node.opacity === undefined ? 1 : node.opacity)
        textEditor.text = node.kind === "text" ? (node.text || "") : ""
    }

    function refreshScene() {
        scene = JSON.parse(sceneBridge.sceneJson)
        page = activePage()
        var availableSlots = slots()
        var stillExists = false
        for (var i = 0; i < availableSlots.length; ++i)
            if (availableSlots[i].id === selectedSlotId)
                stillExists = true
        if (!stillExists)
            selectedSlotId = availableSlots.length ? availableSlots[0].id : ""
        Qt.callLater(syncInspector)
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { window.refreshScene() }
    }

    Component.onCompleted: {
        refreshScene()
        syncInspector()
    }

    Shortcut { sequence: StandardKey.Undo; onActivated: sceneBridge.undo() }
    Shortcut { sequence: StandardKey.Redo; onActivated: sceneBridge.redo() }
    Shortcut { sequence: StandardKey.Delete; onActivated: sceneBridge.dispatch('{"name":"delete"}') }
    Shortcut { sequence: "Ctrl+D"; onActivated: sceneBridge.dispatch('{"name":"duplicate"}') }
    Shortcut { sequence: "Ctrl+G"; onActivated: sceneBridge.dispatch('{"name":"group"}') }
    Shortcut { sequence: "Ctrl+Shift+G"; onActivated: sceneBridge.dispatch('{"name":"ungroup"}') }
    Shortcut { sequence: "G"; onActivated: showGrid = !showGrid }

    header: ToolBar {
        implicitHeight: 58
        background: Rectangle { color: "#FFFFFF"; border.color: "#D9E2EF" }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 7

            ColumnLayout {
                spacing: -1
                Label { text: "SR GRAPHICS ENGINE 2.0"; color: "#0F5BD8"; font.bold: true; font.pixelSize: 10 }
                Label { text: scene.name || "Novo Projeto SR"; color: "#111827"; font.bold: true; font.pixelSize: 14 }
            }
            ToolSeparator {}
            ToolButton { text: "↶"; enabled: scene.editor ? scene.editor.can_undo : false; ToolTip.text: "Desfazer"; ToolTip.visible: hovered; onClicked: sceneBridge.undo() }
            ToolButton { text: "↷"; enabled: scene.editor ? scene.editor.can_redo : false; ToolTip.text: "Refazer"; ToolTip.visible: hovered; onClicked: sceneBridge.redo() }
            ToolSeparator {}
            ToolButton { text: "▦"; checkable: true; checked: showGrid; ToolTip.text: "Grid"; ToolTip.visible: hovered; onClicked: showGrid = checked }
            ToolButton { text: "▤"; checkable: true; checked: showRulers; ToolTip.text: "Réguas"; ToolTip.visible: hovered; onClicked: showRulers = checked }
            ToolButton { text: "Agrupar"; onClicked: sceneBridge.dispatch('{"name":"group"}') }
            ToolButton { text: "Desagrupar"; onClicked: sceneBridge.dispatch('{"name":"ungroup"}') }
            ToolButton { text: "Frente"; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"front"}') }
            ToolButton { text: "Fundo"; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"back"}') }
            ToolButton { text: "Duplicar"; onClicked: sceneBridge.dispatch('{"name":"duplicate"}') }
            ToolSeparator {}
            ToolButton { text: "+ Página"; onClicked: sceneBridge.dispatch('{"name":"add_page"}') }
            ToolButton { text: "⧉ Página"; onClicked: sceneBridge.dispatch('{"name":"duplicate_page"}') }
            Item { Layout.fillWidth: true }
            Rectangle {
                implicitWidth: qualityText.implicitWidth + 20
                implicitHeight: 30
                radius: 5
                color: "#FFF8E6"
                border.color: "#F2D58A"
                Label { id: qualityText; anchors.centerIn: parent; text: "✓ Engine 2 · ALPHA"; color: "#A16207"; font.bold: true; font.pixelSize: 11 }
            }
            Label { text: Math.round(window.zoom * 100) + "%"; color: "#475569"; Layout.preferredWidth: 44; horizontalAlignment: Text.AlignRight }
            Slider { from: 0.12; to: 3.5; value: window.zoom; Layout.preferredWidth: 155; onMoved: window.zoom = value }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.preferredWidth: 310
                SplitView.minimumWidth: 245
                color: "#FFFFFF"
                border.color: "#D9E2EF"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    Label { text: "Studio de Encartes"; font.bold: true; font.pixelSize: 18; color: "#111827" }
                    Label { text: "Produtos, Smart Slots e camadas"; color: "#64748B"; font.pixelSize: 11 }

                    TabBar {
                        id: leftTabs
                        Layout.fillWidth: true
                        TabButton { text: "Produtos" }
                        TabButton { text: "Camadas" }
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: leftTabs.currentIndex

                        ColumnLayout {
                            spacing: 8
                            Label { text: "Destino do produto"; color: "#475569"; font.bold: true; font.pixelSize: 11 }
                            ComboBox {
                                id: slotCombo
                                Layout.fillWidth: true
                                model: slots()
                                textRole: "name"
                                valueRole: "id"
                                onActivated: selectedSlotId = currentValue
                                Component.onCompleted: if (count > 0) selectedSlotId = currentValue
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: "#E6ECF4" }
                            ListView {
                                id: productList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 8
                                model: products()
                                ScrollBar.vertical: ScrollBar {}
                                delegate: Rectangle {
                                    id: productCard
                                    required property var modelData
                                    width: productList.width - 4
                                    height: 84
                                    radius: 6
                                    color: productMouse.containsMouse ? "#F1F6FF" : "#FFFFFF"
                                    border.color: "#D9E4F2"
                                    property var productData: modelData

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 9
                                        spacing: 9
                                        Rectangle {
                                            Layout.preferredWidth: 58
                                            Layout.preferredHeight: 58
                                            radius: 5
                                            color: "#F8FAFC"
                                            border.color: "#E5EAF1"
                                            clip: true
                                            Image {
                                                anchors.fill: parent
                                                anchors.margins: 3
                                                source: localSource(modelData.image_path || modelData.image || "")
                                                fillMode: Image.PreserveAspectFit
                                                asynchronous: true
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Label { Layout.fillWidth: true; text: modelData.display_name || modelData.name || modelData.original_name || "Produto"; color: "#111827"; font.bold: true; font.pixelSize: 11; elide: Text.ElideRight }
                                            Label { text: (modelData.unit || "UN") + (modelData.category ? " · " + modelData.category : ""); color: "#64748B"; font.pixelSize: 10 }
                                            Label { text: modelData.price ? ("R$ " + String(modelData.price).replace(".", ",")) : "Sem preço"; color: "#0F5BD8"; font.bold: true; font.pixelSize: 12 }
                                        }
                                        ToolButton { text: "+"; enabled: selectedSlotId !== ""; onClicked: bindProduct(modelData) }
                                    }
                                    MouseArea {
                                        id: productMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        acceptedButtons: Qt.LeftButton
                                        onDoubleClicked: if (selectedSlotId) bindProduct(productCard.productData)
                                    }
                                }
                                Label { anchors.centerIn: parent; visible: productList.count === 0; text: "Importe uma planilha para carregar produtos."; width: productList.width - 30; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; color: "#94A3B8" }
                            }
                        }

                        ColumnLayout {
                            spacing: 6
                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "Elementos"; font.bold: true; color: "#334155" }
                                Item { Layout.fillWidth: true }
                                Label { text: nodes().length; color: "#64748B" }
                            }
                            ListView {
                                id: layerList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                model: nodes().sort(function(a, b) { return b.z_index - a.z_index })
                                ScrollBar.vertical: ScrollBar {}
                                delegate: ItemDelegate {
                                    required property var modelData
                                    width: layerList.width
                                    highlighted: isSelected(modelData)
                                    text: (modelData.visible === false ? "◌  " : "◉  ") + (modelData.locked ? "🔒  " : "") + (modelData.name || modelData.kind)
                                    onClicked: sceneBridge.selectNodeAdvanced(modelData.id, false, (Qt.application.keyboardModifiers & Qt.ControlModifier) !== 0)
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: workspace
                SplitView.fillWidth: true
                SplitView.fillHeight: true
                color: "#DCE4EF"

                Flickable {
                    id: viewport
                    anchors.fill: parent
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    contentWidth: Math.max(width, (page ? page.width : 1080) * zoom + 280)
                    contentHeight: Math.max(height, (page ? page.height : 1350) * zoom + 250)

                    Item {
                        id: world
                        width: viewport.contentWidth
                        height: viewport.contentHeight

                        Rectangle {
                            id: topRuler
                            visible: showRulers && page
                            x: sheet.x
                            y: sheet.y - 26
                            width: sheet.width
                            height: 24
                            color: "#F8FAFC"
                            border.color: "#C8D3E0"
                            clip: true
                            Repeater {
                                model: page ? Math.ceil(page.width / gridStep) + 1 : 0
                                delegate: Item {
                                    x: index * gridStep * zoom
                                    width: 1
                                    height: topRuler.height
                                    Rectangle { x: 0; y: parent.height - 8; width: 1; height: 8; color: "#64748B" }
                                    Label { x: 3; y: 1; text: Math.round(index * gridStep); color: "#64748B"; font.pixelSize: 8 }
                                }
                            }
                        }

                        Rectangle {
                            id: leftRuler
                            visible: showRulers && page
                            x: sheet.x - 28
                            y: sheet.y
                            width: 26
                            height: sheet.height
                            color: "#F8FAFC"
                            border.color: "#C8D3E0"
                            clip: true
                            Repeater {
                                model: page ? Math.ceil(page.height / gridStep) + 1 : 0
                                delegate: Item {
                                    y: index * gridStep * zoom
                                    width: leftRuler.width
                                    height: 1
                                    Rectangle { x: parent.width - 8; y: 0; width: 8; height: 1; color: "#64748B" }
                                    Label { x: 2; y: 2; text: Math.round(index * gridStep); color: "#64748B"; font.pixelSize: 7; rotation: -90; transformOrigin: Item.TopLeft }
                                }
                            }
                        }

                        Rectangle {
                            id: sheetShadow
                            x: sheet.x + 7
                            y: sheet.y + 8
                            width: sheet.width
                            height: sheet.height
                            color: "#64748B22"
                            radius: 2
                        }

                        Rectangle {
                            id: sheet
                            x: 140
                            y: 90
                            width: (page ? page.width : 1080) * zoom
                            height: (page ? page.height : 1350) * zoom
                            color: page ? page.background : "white"
                            border.color: "#BFCBDA"
                            clip: false

                            Repeater {
                                visible: showGrid
                                model: page ? Math.ceil(page.width / gridStep) + 1 : 0
                                delegate: Rectangle { x: index * gridStep * zoom; y: 0; width: 1; height: sheet.height; color: "#CBD5E144" }
                            }
                            Repeater {
                                visible: showGrid
                                model: page ? Math.ceil(page.height / gridStep) + 1 : 0
                                delegate: Rectangle { x: 0; y: index * gridStep * zoom; width: sheet.width; height: 1; color: "#CBD5E144" }
                            }

                            Repeater {
                                model: page ? nodes().filter(function(n) { return effectiveVisible(n) }).sort(function(a, b) { return a.z_index - b.z_index }) : []
                                delegate: Item {
                                    id: nodeItem
                                    required property var modelData
                                    x: modelData.transform.x * zoom
                                    y: modelData.transform.y * zoom
                                    width: Math.max(1, modelData.transform.width * zoom)
                                    height: Math.max(1, modelData.transform.height * zoom)
                                    rotation: Number(modelData.transform.rotation || 0)
                                    opacity: effectiveOpacity(modelData)
                                    visible: modelData.kind !== "group" || isSelected(modelData)

                                    Rectangle {
                                        anchors.fill: parent
                                        visible: modelData.kind === "rect" || modelData.kind === "group"
                                        color: modelData.kind === "group" ? "transparent" : (modelData.style.fill || "transparent")
                                        border.width: modelData.kind === "group" ? 1 : Number(modelData.style.stroke_width || 0) * zoom
                                        border.color: modelData.kind === "group" ? "#0F5BD866" : (modelData.style.stroke || "transparent")
                                        radius: Number(modelData.style.radius || 0) * zoom
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        visible: modelData.kind === "ellipse"
                                        radius: width / 2
                                        color: modelData.style.fill || "transparent"
                                        border.width: Number(modelData.style.stroke_width || 0) * zoom
                                        border.color: modelData.style.stroke || "transparent"
                                    }
                                    Text {
                                        anchors.fill: parent
                                        visible: modelData.kind === "text"
                                        text: modelData.text || ""
                                        color: modelData.style.color || "#111827"
                                        font.family: modelData.style.font_family || "Segoe UI"
                                        font.pixelSize: Math.max(4, Number(modelData.style.font_size || 20) * (String(modelData.style.font_size_unit || "pt") === "pt" ? 1.333333 : 1) * zoom)
                                        font.bold: Number(modelData.style.font_weight || 400) >= 700
                                        font.italic: !!modelData.style.italic
                                        horizontalAlignment: modelData.style.align === "left" ? Text.AlignLeft : modelData.style.align === "right" ? Text.AlignRight : Text.AlignHCenter
                                        verticalAlignment: modelData.style.v_align === "top" ? Text.AlignTop : modelData.style.v_align === "bottom" ? Text.AlignBottom : Text.AlignVCenter
                                        wrapMode: modelData.style.nowrap ? Text.NoWrap : Text.WordWrap
                                        fontSizeMode: modelData.style.fit_inside_box ? Text.Fit : Text.FixedSize
                                        minimumPixelSize: Math.max(3, 4 * zoom)
                                        elide: modelData.style.fit_inside_box ? Text.ElideNone : Text.ElideRight
                                    }
                                    Image {
                                        anchors.fill: parent
                                        visible: modelData.kind === "image" || modelData.kind === "background"
                                        source: imageSource(modelData)
                                        fillMode: modelData.style.fit === "cover" ? Image.PreserveAspectCrop : modelData.style.fit === "fill" ? Image.Stretch : Image.PreserveAspectFit
                                        asynchronous: true
                                        cache: true
                                        mipmap: true
                                        smooth: true
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        drag.target: parent
                                        enabled: !effectiveLocked(modelData)
                                        preventStealing: true
                                        onPressed: sceneBridge.selectNodeAdvanced(modelData.id, (mouse.modifiers & Qt.ShiftModifier) !== 0, (mouse.modifiers & Qt.ControlModifier) !== 0)
                                        onReleased: {
                                            var dx = (parent.x / zoom) - Number(modelData.transform.x)
                                            var dy = (parent.y / zoom) - Number(modelData.transform.y)
                                            if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001)
                                                sceneBridge.moveSelectionAtZoom(dx, dy, zoom)
                                        }
                                        onDoubleClicked: if (modelData.kind === "text") textEditor.forceActiveFocus()
                                    }
                                }
                            }

                            Repeater {
                                model: slots()
                                delegate: Item {
                                    required property var modelData
                                    property var bounds: slotBounds(modelData)
                                    x: bounds.x * zoom
                                    y: bounds.y * zoom
                                    width: bounds.width * zoom
                                    height: bounds.height * zoom
                                    visible: width > 2 && height > 2
                                    z: 100000
                                    Rectangle {
                                        anchors.fill: parent
                                        color: selectedSlotId === modelData.id ? "#0F5BD811" : "transparent"
                                        border.width: selectedSlotId === modelData.id ? 2 : 1
                                        border.color: selectedSlotId === modelData.id ? "#0F5BD8" : "#0F5BD855"
                                        radius: 4
                                    }
                                    Label {
                                        x: 4; y: 4
                                        text: modelData.name || "Smart Slot"
                                        color: "white"
                                        font.bold: true
                                        font.pixelSize: 9
                                        padding: 3
                                        background: Rectangle { color: selectedSlotId === modelData.id ? "#0F5BD8" : "#64748BAA"; radius: 3 }
                                    }
                                    MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton; onClicked: selectedSlotId = modelData.id }
                                }
                            }

                            Item {
                                id: selectionOverlay
                                visible: anchorNode && page && effectiveVisible(anchorNode)
                                x: visible ? anchorNode.transform.x * zoom : 0
                                y: visible ? anchorNode.transform.y * zoom : 0
                                width: visible ? Math.max(1, anchorNode.transform.width * zoom) : 1
                                height: visible ? Math.max(1, anchorNode.transform.height * zoom) : 1
                                rotation: visible ? Number(anchorNode.transform.rotation || 0) : 0
                                z: 200000

                                Rectangle { anchors.fill: parent; color: "transparent"; border.width: 2; border.color: "#0F5BD8" }
                                Rectangle { x: parent.width / 2; y: -30; width: 1; height: 30; color: "#0F5BD8" }
                                Rectangle { width: 13; height: 13; radius: 7; x: parent.width / 2 - 6.5; y: -42; color: "white"; border.width: 2; border.color: "#0F5BD8" }

                                Repeater {
                                    model: [
                                        {"dir":"nw","fx":0,"fy":0,"cursor":Qt.SizeFDiagCursor},
                                        {"dir":"n","fx":0.5,"fy":0,"cursor":Qt.SizeVerCursor},
                                        {"dir":"ne","fx":1,"fy":0,"cursor":Qt.SizeBDiagCursor},
                                        {"dir":"e","fx":1,"fy":0.5,"cursor":Qt.SizeHorCursor},
                                        {"dir":"se","fx":1,"fy":1,"cursor":Qt.SizeFDiagCursor},
                                        {"dir":"s","fx":0.5,"fy":1,"cursor":Qt.SizeVerCursor},
                                        {"dir":"sw","fx":0,"fy":1,"cursor":Qt.SizeBDiagCursor},
                                        {"dir":"w","fx":0,"fy":0.5,"cursor":Qt.SizeHorCursor}
                                    ]
                                    delegate: Rectangle {
                                        required property var modelData
                                        width: 11; height: 11; radius: 2
                                        x: modelData.fx * selectionOverlay.width - width / 2
                                        y: modelData.fy * selectionOverlay.height - height / 2
                                        color: "white"
                                        border.width: 2
                                        border.color: "#0F5BD8"
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: modelData.cursor
                                            preventStealing: true
                                            property real pressX: 0
                                            property real pressY: 0
                                            onPressed: { pressX = mouse.x; pressY = mouse.y }
                                            onReleased: {
                                                if (!anchorNode) return
                                                sceneBridge.dispatch(JSON.stringify({
                                                    "name": "resize_handle",
                                                    "node_id": anchorNode.id,
                                                    "handle": modelData.dir,
                                                    "dx": (mouse.x - pressX) / zoom,
                                                    "dy": (mouse.y - pressY) / zoom,
                                                    "keep_ratio": (mouse.modifiers & Qt.ShiftModifier) !== 0
                                                }))
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    WheelHandler {
                        acceptedModifiers: Qt.ControlModifier
                        onWheel: function(event) {
                            var factor = event.angleDelta.y > 0 ? 1.10 : 0.90
                            window.zoom = Math.max(0.12, Math.min(3.5, window.zoom * factor))
                        }
                    }
                }
            }

            Rectangle {
                SplitView.preferredWidth: 330
                SplitView.minimumWidth: 275
                color: "#FFFFFF"
                border.color: "#D9E2EF"

                ScrollView {
                    anchors.fill: parent
                    clip: true
                    ColumnLayout {
                        width: parent.width
                        spacing: 10
                        anchors.margins: 14

                        Label { text: "Propriedades"; font.bold: true; font.pixelSize: 18; color: "#111827" }
                        Label { id: inspectorName; text: "Nada selecionado"; color: "#0F5BD8"; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                        Label { text: sceneBridge.status; color: "#64748B"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#E6ECF4" }

                        GridLayout {
                            columns: 2
                            columnSpacing: 8
                            rowSpacing: 7
                            Layout.fillWidth: true
                            Label { text: "X"; color: "#64748B" }
                            TextField { id: xField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Y"; color: "#64748B" }
                            TextField { id: yField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Largura"; color: "#64748B" }
                            TextField { id: wField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Altura"; color: "#64748B" }
                            TextField { id: hField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Rotação"; color: "#64748B" }
                            TextField { id: rotationField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                        }
                        Button {
                            text: "Aplicar geometria"
                            Layout.fillWidth: true
                            enabled: !!anchorNode
                            onClicked: {
                                if (!anchorNode) return
                                sceneBridge.dispatch(JSON.stringify({"name":"resize","node_id":anchorNode.id,"x":Number(xField.text),"y":Number(yField.text),"width":Number(wField.text),"height":Number(hField.text)}))
                                sceneBridge.dispatch(JSON.stringify({"name":"rotate","angle":Number(rotationField.text)}))
                            }
                        }

                        Label { text: "Opacidade"; color: "#475569"; font.bold: true }
                        Slider { id: opacityField; from: 0; to: 1; stepSize: 0.01; value: 1; Layout.fillWidth: true; onMoved: if (anchorNode) sceneBridge.dispatch(JSON.stringify({"name":"opacity","value":value})) }

                        ColumnLayout {
                            visible: anchorNode && anchorNode.kind === "text"
                            Layout.fillWidth: true
                            Label { text: "Texto"; color: "#475569"; font.bold: true }
                            TextArea { id: textEditor; Layout.fillWidth: true; Layout.preferredHeight: 90; wrapMode: TextEdit.Wrap }
                            Button { text: "Aplicar texto"; Layout.fillWidth: true; onClicked: if (anchorNode) sceneBridge.editText(anchorNode.id, textEditor.text) }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: "#E6ECF4" }
                        Label { text: "Organizar"; color: "#475569"; font.bold: true }
                        GridLayout {
                            columns: 3
                            Layout.fillWidth: true
                            Button { text: "Esq."; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"left"}') }
                            Button { text: "Centro"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"center"}') }
                            Button { text: "Dir."; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"right"}') }
                            Button { text: "Topo"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"top"}') }
                            Button { text: "Meio"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"middle"}') }
                            Button { text: "Base"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"align","mode":"bottom"}') }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: "Distribuir H"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"distribute","axis":"horizontal"}') }
                            Button { text: "Distribuir V"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"distribute","axis":"vertical"}') }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: "Bloquear"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"lock","value":true}') }
                            Button { text: "Desbloquear"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"lock","value":false}') }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: "Ocultar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"hide","value":true}') }
                            Button { text: "Mostrar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"hide","value":false}') }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: "▲ Frente"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"front"}') }
                            Button { text: "▼ Fundo"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"back"}') }
                        }
                        Item { Layout.preferredHeight: 8 }
                        Label { text: "Qt Quick / RHI · interface preparada para GPU dedicada"; color: "#0F5BD8"; font.bold: true; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            color: "#FFFFFF"
            border.color: "#D9E2EF"
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 7
                Label { text: "Páginas"; font.bold: true; color: "#334155" }
                Repeater {
                    model: scene.pages || []
                    delegate: Button {
                        required property var modelData
                        text: modelData.name || ("Página " + (index + 1))
                        checked: modelData.id === scene.active_page_id
                        checkable: true
                        onClicked: sceneBridge.dispatch(JSON.stringify({"name":"select_page","page_id":modelData.id}))
                    }
                }
                Button { text: "+"; onClicked: sceneBridge.dispatch('{"name":"add_page"}') }
                Item { Layout.fillWidth: true }
                Label { text: "Snap ✓  ·  Grid " + (showGrid ? "✓" : "—") + "  ·  Réguas " + (showRulers ? "✓" : "—"); color: "#64748B"; font.pixelSize: 10 }
            }
        }
    }
}
