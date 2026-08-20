import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: window
    width: 1760
    height: 1020
    minimumWidth: 1180
    minimumHeight: 720
    visible: true
    title: "Studio de Encartes · SR Graphics Engine 2"
    color: theme.appBackground

    StudioTheme { id: theme }

    property var scene: JSON.parse(sceneBridge.sceneJson)
    property var page: activePage()
    property real zoom: 0.72
    property bool showGrid: true
    property bool showRulers: true
    property real gridStep: 50
    property string selectedSlotId: ""
    property string hoveredSlotId: ""
    property bool smartSlotInspectionMode: false
    property bool smartSlotEditMode: false
    property bool smartSlotSnap: true
    property real smartSlotLastCommitMs: 0
    property int smartSlotPreviewEvents: 0
    property int smartSlotPreviewUpdates: 0
    property string smartSlotInteractionKind: ""
    property bool itemSlotPreviewActive: false
    property string itemSlotPreviewSlotId: ""
    property var itemSlotPreviewStartBounds: ({"x":0,"y":0,"width":1,"height":1})
    property var itemSlotPreviewBounds: ({"x":0,"y":0,"width":1,"height":1})
    property int itemSlotPreviewEvents: 0
    property int itemSlotPreviewUpdates: 0
    property int itemSlotBackendCommits: 0
    property string itemSlotInteractionKind: ""
    property var anchorNode: selectedNode()
    property var draggedProduct: null
    property bool productDragActive: false
    property real productDragX: 0
    property real productDragY: 0
    property string dragHoverSlotId: ""

    // Visual-only Studio state ported from PR #91. None of these properties
    // participate in ItemSlot geometry or dispatch.
    property string productSearch: ""
    property string productCategory: "Todos"
    property string leftSection: "Produtos"
    readonly property bool compactUi: width < 1500
    readonly property bool tightUi: width < 1320
    readonly property real studioLeftDockWidth: tightUi ? 300 : (compactUi ? 334 : 396)
    readonly property real studioInspectorWidth: tightUi ? 276 : (compactUi ? 304 : 330)

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

    function manualItemSlotForNode(nodeId) {
        if (!page || !nodeId)
            return null
        var current = page.nodes[String(nodeId)]
        var guard = 0
        while (current && guard++ < 128) {
            var metadata = current.metadata || {}
            var slotId = String(metadata.item_slot_id || "")
            if (slotId && page.slots && page.slots[slotId]) {
                var slot = page.slots[slotId]
                var slotMetadata = slot.metadata || {}
                if (slotMetadata.manual_item_slot)
                    return slot
            }
            var parentId = String(current.parent_id || "")
            current = parentId && page.nodes[parentId] ? page.nodes[parentId] : null
        }
        return null
    }

    function itemSlotDisplayTransform(node) {
        var t = node && node.transform ? node.transform : {"x":0,"y":0,"width":1,"height":1}
        var base = {"x":Number(t.x || 0),"y":Number(t.y || 0),"width":Math.max(1,Number(t.width || 1)),"height":Math.max(1,Number(t.height || 1))}
        if (!itemSlotPreviewActive || !node)
            return base
        var slot = manualItemSlotForNode(node.id)
        if (!slot || String(slot.id || "") !== itemSlotPreviewSlotId)
            return base
        var start = itemSlotPreviewStartBounds
        var preview = itemSlotPreviewBounds
        var startW = Math.max(0.000001, Number(start.width || 1))
        var startH = Math.max(0.000001, Number(start.height || 1))
        var sx = Math.max(0.000001, Number(preview.width || 1)) / startW
        var sy = Math.max(0.000001, Number(preview.height || 1)) / startH
        return {
            "x":Number(preview.x || 0) + (base.x - Number(start.x || 0)) * sx,
            "y":Number(preview.y || 0) + (base.y - Number(start.y || 0)) * sy,
            "width":Math.max(1, base.width * sx),
            "height":Math.max(1, base.height * sy)
        }
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
        var metadata = node.metadata || {}
        var assetSource = ""
        if (node.asset_id && scene.assets && scene.assets[node.asset_id])
            assetSource = scene.assets[node.asset_id].source || ""
        return localSource(metadata.bound_image_source || metadata.source_url || assetSource)
    }

    function productImageSource(product) {
        if (!product)
            return ""
        return localSource(product.image_path || product.image || product.image_url || product.source || "")
    }

    function productMatchesCategory(product, category) {
        if (category === "Todos")
            return true
        var text = String(product.category || product.department || product.section || "").toLowerCase()
        if (category === "Carnes")
            return text.indexOf("carne") >= 0 || text.indexOf("açou") >= 0 || text.indexOf("frango") >= 0 || text.indexOf("suí") >= 0 || text.indexOf("bov") >= 0
        if (category === "Bebidas")
            return text.indexOf("beb") >= 0 || text.indexOf("cerve") >= 0 || text.indexOf("refriger") >= 0 || text.indexOf("suco") >= 0
        if (category === "Mercearia")
            return text.indexOf("merce") >= 0 || text.indexOf("alimento") >= 0 || text.indexOf("seco") >= 0
        if (category === "Limpeza")
            return text.indexOf("limp") >= 0 || text.indexOf("hig") >= 0
        return true
    }

    function filteredProducts() {
        var query = String(productSearch || "").trim().toLowerCase()
        return products().filter(function(product) {
            if (!productMatchesCategory(product, productCategory))
                return false
            if (!query)
                return true
            var haystack = [product.display_name, product.name, product.original_name, product.category, product.unit].join(" ").toLowerCase()
            return haystack.indexOf(query) >= 0
        })
    }

    function textInset(style, key) {
        var insets = style && style.text_insets ? style.text_insets : {}
        return Math.max(0, Number(insets[key] || 0)) * zoom
    }

    function textLineHeightMode(style) {
        if (style && Number(style.line_spacing_px || 0) > 0)
            return Text.FixedHeight
        return Text.ProportionalHeight
    }

    function textLineHeight(style) {
        if (!style)
            return 1.0
        var fixed = Number(style.line_spacing_px || 0)
        if (fixed > 0)
            return Math.max(1, fixed * zoom)
        var proportional = Number(style.line_spacing_percent || 0)
        if (proportional > 10)
            proportional = proportional / 100.0
        return proportional > 0 ? proportional : 1.0
    }

    function hasCustomPath(node) {
        return !!(node && node.metadata && node.metadata.custom_path && node.metadata.custom_path.paths && node.metadata.custom_path.paths.length)
    }

    function slotBounds(slot) {
        if (!page || !slot)
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        var slotMetadata = slot.metadata || {}
        if (slotMetadata.manual_item_slot) {
            var rootId = String(slotMetadata.root_node_id || "")
            var rootNode = rootId && page.nodes ? page.nodes[rootId] : null
            if (rootNode && rootNode.transform) {
                var rt = rootNode.transform
                return {"x": Number(rt.x || 0), "y": Number(rt.y || 0), "width": Math.max(1, Number(rt.width || 1)), "height": Math.max(1, Number(rt.height || 1))}
            }
        }
        var effective = slot.metadata ? slot.metadata.effective_bounds : null
        if (effective) {
            var ew = Math.max(0, Number(effective.width || 0))
            var eh = Math.max(0, Number(effective.height || 0))
            if (ew > 0 && eh > 0)
                return {"x": Number(effective.x || 0), "y": Number(effective.y || 0), "width": ew, "height": eh}
        }
        var cardId = slot.metadata ? String(slot.metadata.semantic_product_card_id || "") : ""
        var blocks = page.metadata && page.metadata.semantic_blocks ? page.metadata.semantic_blocks : {}
        if (cardId && blocks[cardId] && blocks[cardId].bounds) {
            var semantic = blocks[cardId].bounds
            var sw = Math.max(0, Number(semantic.width || 0))
            var sh = Math.max(0, Number(semantic.height || 0))
            if (sw > 0 && sh > 0)
                return {"x": Number(semantic.x || 0), "y": Number(semantic.y || 0), "width": sw, "height": sh}
        }
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

    function productLabel(product) {
        if (!product)
            return "Produto"
        return String(product.display_name || product.name || product.original_name || "Produto")
    }

    function slotAtDocumentPoint(x, y) {
        var available = slots()
        var winner = null
        var winnerArea = 1e30
        for (var i = 0; i < available.length; ++i) {
            var bounds = slotBounds(available[i])
            if (x < bounds.x || y < bounds.y || x > bounds.x + bounds.width || y > bounds.y + bounds.height)
                continue
            var area = Math.max(1, bounds.width * bounds.height)
            if (area < winnerArea) {
                winner = available[i]
                winnerArea = area
            }
        }
        return winner
    }

    function beginProductDrag(sourceItem, mouseX, mouseY, product) {
        draggedProduct = product
        productDragActive = true
        updateProductDrag(sourceItem, mouseX, mouseY, product)
    }

    function updateProductDrag(sourceItem, mouseX, mouseY, product) {
        if (!sourceItem || !product)
            return
        draggedProduct = product
        var globalPoint = sourceItem.mapToItem(window.contentItem, mouseX, mouseY)
        productDragX = globalPoint.x
        productDragY = globalPoint.y
        if (!page || !sheet) {
            dragHoverSlotId = ""
            return
        }
        var sheetPoint = sourceItem.mapToItem(sheet, mouseX, mouseY)
        if (sheetPoint.x < 0 || sheetPoint.y < 0 || sheetPoint.x > sheet.width || sheetPoint.y > sheet.height) {
            dragHoverSlotId = ""
            return
        }
        var target = slotAtDocumentPoint(sheetPoint.x / zoom, sheetPoint.y / zoom)
        dragHoverSlotId = target ? target.id : ""
    }

    function finishProductDrag(sourceItem, mouseX, mouseY, product) {
        if (!sourceItem || !product || !page || !sheet) {
            cancelProductDrag()
            return
        }
        var point = sourceItem.mapToItem(sheet, mouseX, mouseY)
        if (point.x >= 0 && point.y >= 0 && point.x <= sheet.width && point.y <= sheet.height) {
            var productId = String(product.id || product.product_id || "")
            if (productId) {
                var resultRaw = sceneBridge.dispatch(JSON.stringify({
                    "name": "drop_product",
                    "product_id": productId,
                    "x": point.x / zoom,
                    "y": point.y / zoom,
                    "magnet_distance": 12 / Math.max(zoom, 0.01)
                }))
                try {
                    var result = JSON.parse(resultRaw)
                    if (result.ok && result.payload && result.payload.drop_target)
                        selectedSlotId = String(result.payload.drop_target.slot_id || selectedSlotId)
                } catch (error) {
                    console.warn("SR drag-and-drop: resposta inválida", error)
                }
            }
        }
        cancelProductDrag()
    }

    function cancelProductDrag() {
        productDragActive = false
        draggedProduct = null
        dragHoverSlotId = ""
    }

    function bindProduct(product) {
        if (!selectedSlotId) {
            sceneBridge.dispatch(JSON.stringify({"name": "clear_selection"}))
            return
        }
        sceneBridge.dispatch(JSON.stringify({"name": "bind_product", "slot_id": selectedSlotId, "product_id": product.id}))
    }

    function fitToViewport() {
        if (!page || !viewport)
            return
        var usableWidth = Math.max(220, viewport.width - 160)
        var usableHeight = Math.max(220, viewport.height - 150)
        var target = Math.min(usableWidth / Math.max(1, page.width), usableHeight / Math.max(1, page.height))
        zoom = Math.max(0.12, Math.min(3.5, target))
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
            selectedSlotId = ""
        hoveredSlotId = ""
        dragHoverSlotId = ""
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

    header: Item {
        implicitHeight: 104

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 52
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#201B4C" }
                GradientStop { position: 0.23; color: "#5B3FEA" }
                GradientStop { position: 0.72; color: "#477AF1" }
                GradientStop { position: 1.0; color: "#18BEBB" }
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 14
                spacing: 14

                RowLayout {
                    Layout.preferredWidth: window.tightUi ? 265 : 330
                    spacing: 9
                    Rectangle {
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        radius: 8
                        color: "#FFFFFF16"
                        border.width: 1
                        border.color: "#FFFFFF22"
                        Label { anchors.centerIn: parent; text: "SR"; color: "white"; font.pixelSize: 10; font.bold: true }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: -1
                        Label { text: "Studio de Encartes"; color: "#FFFFFF"; font.pixelSize: 15; font.bold: true }
                        Label { visible: !window.tightUi; text: "SR Graphics Engine 2"; color: "#DCD9FF"; font.pixelSize: 9 }
                    }
                }

                Repeater {
                    model: ["Arquivo", "Editar", "Ver", "Inserir", "Formato", "Página", "Ajuda"]
                    delegate: Label {
                        required property var modelData
                        visible: !window.compactUi || index < 5
                        text: modelData
                        color: "white"
                        font.pixelSize: 11
                    }
                }
                Item { Layout.fillWidth: true }
                Label {
                    Layout.maximumWidth: window.compactUi ? 190 : 330
                    text: scene.name || "Novo Projeto SR"
                    color: "white"
                    font.bold: true
                    font.pixelSize: 11
                    elide: Text.ElideMiddle
                    horizontalAlignment: Text.AlignRight
                }
                Rectangle { Layout.preferredWidth: 30; Layout.preferredHeight: 30; radius: 15; color: "#FFFFFFE8"; Label { anchors.centerIn: parent; text: "SR"; color: theme.primary; font.pixelSize: 9; font.bold: true } }
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 52
            color: "#FFFFFF"
            border.color: theme.border

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 5

                ToolButton { text: "↶"; enabled: scene.editor ? scene.editor.can_undo : false; ToolTip.text: "Desfazer"; ToolTip.visible: hovered; onClicked: sceneBridge.undo() }
                ToolButton { text: "↷"; enabled: scene.editor ? scene.editor.can_redo : false; ToolTip.text: "Refazer"; ToolTip.visible: hovered; onClicked: sceneBridge.redo() }
                ToolSeparator {}
                ToolButton { text: "▦"; checkable: true; checked: showGrid; ToolTip.text: "Grid"; ToolTip.visible: hovered; onClicked: showGrid = checked }
                ToolButton { text: "▤"; checkable: true; checked: showRulers; ToolTip.text: "Réguas"; ToolTip.visible: hovered; onClicked: showRulers = checked }
                ToolButton { text: window.tightUi ? "Slots" : "Smart Slots"; checkable: true; checked: smartSlotInspectionMode; onClicked: smartSlotInspectionMode = checked }
                ToolButton {
                    text: window.compactUi ? "Ajustar Slot" : "Ajustar Smart Slot"
                    checkable: true
                    checked: smartSlotEditMode
                    onClicked: {
                        smartSlotEditMode = checked
                        if (checked) smartSlotInspectionMode = true
                    }
                }
                ToolButton { text: "Snap"; visible: smartSlotEditMode; checkable: true; checked: smartSlotSnap; onClicked: smartSlotSnap = checked }
                ToolButton { text: "Restaurar"; visible: smartSlotEditMode && selectedSlotId !== "" && !window.tightUi; onClicked: sceneBridge.dispatch(JSON.stringify({"name":"restore_smart_slot_auto","slot_id":selectedSlotId})) }
                ToolSeparator {}
                ToolButton { text: "Agrupar"; visible: !window.tightUi; onClicked: sceneBridge.dispatch('{"name":"group"}') }
                ToolButton { text: "Desagrupar"; visible: !window.tightUi; onClicked: sceneBridge.dispatch('{"name":"ungroup"}') }
                ToolButton { text: "Frente"; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"front"}') }
                ToolButton { text: "Fundo"; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"back"}') }
                ToolButton { text: "Duplicar"; onClicked: sceneBridge.dispatch('{"name":"duplicate"}') }
                Item { Layout.fillWidth: true }
                Button { text: "+ Página"; onClicked: sceneBridge.dispatch('{"name":"add_page"}') }
                Label { visible: !window.tightUi; text: sceneBridge.status; color: theme.textMuted; font.pixelSize: 9; Layout.maximumWidth: 220; elide: Text.ElideRight }
            }
        }
    }

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        Rectangle {
            id: leftDock
            SplitView.preferredWidth: window.studioLeftDockWidth
            SplitView.minimumWidth: window.tightUi ? 292 : 310
            SplitView.maximumWidth: 430
            color: theme.navPanel

            RowLayout {
                anchors.fill: parent
                spacing: 0

                StudioSidebar {
                    Layout.preferredWidth: window.tightUi ? 68 : theme.sidebarWidth
                    Layout.fillHeight: true
                    theme: theme
                    currentSection: window.leftSection
                    onSectionRequested: function(section) { window.leftSection = section }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: theme.navPanel
                    Rectangle { anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 1; color: theme.navBorder }

                    StackLayout {
                        anchors.fill: parent
                        currentIndex: window.leftSection === "Produtos" ? 0 : 1

                        ColumnLayout {
                            anchors.margins: window.tightUi ? 10 : 14
                            spacing: 9

                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Label { text: "Produtos"; color: theme.navText; font.pixelSize: theme.fontTitle; font.bold: true }
                                    Label { text: "Importados da planilha"; color: theme.navMuted; font.pixelSize: theme.fontSmall }
                                }
                                Rectangle {
                                    implicitWidth: productCount.implicitWidth + 16
                                    implicitHeight: 25
                                    radius: theme.radiusPill
                                    color: "#FFFFFF12"
                                    Label { id: productCount; anchors.centerIn: parent; text: products().length; color: "#DCE3FA"; font.pixelSize: 9; font.bold: true }
                                }
                            }

                            ComboBox {
                                id: slotCombo
                                Layout.fillWidth: true
                                Layout.preferredHeight: 34
                                model: slots()
                                textRole: "name"
                                valueRole: "id"
                                onActivated: selectedSlotId = currentValue
                            }

                            TextField {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 34
                                placeholderText: "Buscar produto..."
                                color: "#EAF0FF"
                                placeholderTextColor: "#9EACCD"
                                leftPadding: 12
                                rightPadding: 10
                                font.pixelSize: theme.fontSmall
                                onTextChanged: window.productSearch = text
                                background: Rectangle { radius: theme.radiusSmall; color: "#0F1B49"; border.width: 1; border.color: theme.navBorder }
                            }

                            Flickable {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 31
                                contentWidth: chipsRow.implicitWidth
                                contentHeight: height
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                Row {
                                    id: chipsRow
                                    spacing: 5
                                    Repeater {
                                        model: ["Todos", "Carnes", "Bebidas", "Mercearia", "Limpeza"]
                                        delegate: StudioChip {
                                            required property var modelData
                                            theme: theme
                                            text: modelData
                                            active: window.productCategory === modelData
                                            onClicked: window.productCategory = modelData
                                        }
                                    }
                                }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.navBorder }

                            ListView {
                                id: productList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 6
                                model: filteredProducts()
                                reuseItems: true
                                cacheBuffer: 250
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                delegate: ProductListItem {
                                    required property var modelData
                                    width: Math.max(120, productList.width - 8)
                                    theme: theme
                                    productData: modelData
                                    imageSource: productImageSource(modelData)
                                    canBind: selectedSlotId !== ""
                                    onBindRequested: function(product) { bindProduct(product) }
                                    onDragStarted: function(sourceItem, mouseX, mouseY, product) { beginProductDrag(sourceItem, mouseX, mouseY, product) }
                                    onDragUpdated: function(sourceItem, mouseX, mouseY, product) { updateProductDrag(sourceItem, mouseX, mouseY, product) }
                                    onDragFinished: function(sourceItem, mouseX, mouseY, product) { finishProductDrag(sourceItem, mouseX, mouseY, product) }
                                    onDragCanceled: cancelProductDrag()
                                }
                                Label {
                                    anchors.centerIn: parent
                                    visible: productList.count === 0
                                    text: products().length === 0 ? "Importe uma planilha para carregar produtos." : "Nenhum produto corresponde aos filtros."
                                    width: Math.max(120, productList.width - 30)
                                    wrapMode: Text.WordWrap
                                    horizontalAlignment: Text.AlignHCenter
                                    color: theme.navMuted
                                    font.pixelSize: theme.fontSmall
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 22
                                Label { text: filteredProducts().length + " de " + products().length + " produtos"; color: theme.navMuted; font.pixelSize: theme.fontTiny }
                                Item { Layout.fillWidth: true }
                                Label { text: "↻"; color: theme.navMuted; font.pixelSize: 12 }
                            }
                        }

                        ColumnLayout {
                            anchors.margins: 16
                            spacing: 10
                            Label { text: window.leftSection; color: theme.navText; font.pixelSize: theme.fontTitle; font.bold: true }
                            Label { Layout.fillWidth: true; text: "A navegação visual foi preservada sem criar novos backends nesta reconciliação."; color: theme.navMuted; font.pixelSize: theme.fontSmall; wrapMode: Text.WordWrap }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: workspace
            SplitView.fillWidth: true
            SplitView.fillHeight: true
            SplitView.minimumWidth: 420
            color: theme.workspace

            Rectangle {
                id: workspaceHeader
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 42
                color: "#F8FAFD"
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: theme.border }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 14
                    spacing: 8
                    Label { text: page ? (page.name || "Encarte") : "Encarte"; color: theme.text; font.pixelSize: 11; font.bold: true }
                    Rectangle { implicitWidth: pageSizeLabel.implicitWidth + 14; implicitHeight: 22; radius: theme.radiusPill; color: theme.surface; border.width: 1; border.color: theme.border; Label { id: pageSizeLabel; anchors.centerIn: parent; text: page ? (Math.round(page.width) + " × " + Math.round(page.height)) : "—"; color: theme.textMuted; font.pixelSize: theme.fontTiny } }
                    Item { Layout.fillWidth: true }
                    Label { text: "Canvas"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                }
            }

            Flickable {
                id: viewport
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: workspaceHeader.bottom
                anchors.bottom: parent.bottom
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
                        color: theme.ruler
                        border.color: theme.border
                        clip: true
                        Repeater {
                            model: page ? Math.ceil(page.width / gridStep) + 1 : 0
                            delegate: Item {
                                x: index * gridStep * zoom
                                width: 1
                                height: topRuler.height
                                Rectangle { x: 0; y: parent.height - 8; width: 1; height: 8; color: theme.rulerTick }
                                Label { x: 3; y: 1; text: Math.round(index * gridStep); color: theme.rulerTick; font.pixelSize: 8 }
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
                        color: theme.ruler
                        border.color: theme.border
                        clip: true
                        Repeater {
                            model: page ? Math.ceil(page.height / gridStep) + 1 : 0
                            delegate: Item {
                                y: index * gridStep * zoom
                                width: leftRuler.width
                                height: 1
                                Rectangle { x: parent.width - 8; y: 0; width: 8; height: 1; color: theme.rulerTick }
                                Label { x: 2; y: 2; text: Math.round(index * gridStep); color: theme.rulerTick; font.pixelSize: 7; rotation: -90; transformOrigin: Item.TopLeft }
                            }
                        }
                    }

                    Rectangle {
                        id: sheetShadow
                        x: sheet.x + 8
                        y: sheet.y + 9
                        width: sheet.width
                        height: sheet.height
                        color: theme.shadowMedium
                        radius: 7
                    }

                    Rectangle {
                        id: sheet
                        x: Math.max(92, (world.width - width) / 2)
                        y: 78
                        width: (page ? page.width : 1080) * zoom
                        height: (page ? page.height : 1350) * zoom
                        color: page ? page.background : "white"
                        border.color: productDragActive && dragHoverSlotId ? theme.dropTarget : theme.borderStrong
                        border.width: productDragActive && dragHoverSlotId ? 2 : 1
                        radius: 5
                        clip: false

                        Repeater {
                            visible: showGrid
                            model: page ? Math.ceil(page.width / gridStep) + 1 : 0
                            delegate: Rectangle { x: index * gridStep * zoom; y: 0; width: 1; height: sheet.height; color: "#CBD5E133" }
                        }
                        Repeater {
                            visible: showGrid
                            model: page ? Math.ceil(page.height / gridStep) + 1 : 0
                            delegate: Rectangle { x: 0; y: index * gridStep * zoom; width: sheet.width; height: 1; color: "#CBD5E133" }
                        }

                        Repeater {
                            model: page ? nodes().filter(function(n) { return effectiveVisible(n) }).sort(function(a, b) { return a.z_index - b.z_index }) : []
                            delegate: Item {
                                id: nodeItem
                                required property var modelData
                                property var displayTransform: window.itemSlotDisplayTransform(modelData)
                                x: displayTransform.x * zoom
                                y: displayTransform.y * zoom
                                width: Math.max(1, displayTransform.width * zoom)
                                height: Math.max(1, displayTransform.height * zoom)
                                rotation: Number(modelData.transform.rotation || 0)
                                opacity: effectiveOpacity(modelData)
                                visible: modelData.kind !== "group" || isSelected(modelData)

                                Rectangle {
                                    anchors.fill: parent
                                    visible: (modelData.kind === "rect" && !hasCustomPath(modelData)) || modelData.kind === "group"
                                    color: modelData.kind === "group" ? "transparent" : (modelData.style.fill || "transparent")
                                    border.width: modelData.kind === "group" ? 1 : Number(modelData.style.stroke_width || 0) * zoom
                                    border.color: modelData.kind === "group" ? "#0F5BD866" : (modelData.style.stroke || "transparent")
                                    radius: modelData.kind === "group" ? 0 : (Number(modelData.style.radius || 0) > 0 ? Number(modelData.style.radius) * zoom : Number(modelData.style.radius_ratio || 0) * Math.min(width, height))
                                }
                                Canvas {
                                    id: customPathCanvas
                                    anchors.fill: parent
                                    visible: (modelData.kind === "rect" || modelData.kind === "path") && hasCustomPath(modelData)
                                    renderTarget: Canvas.FramebufferObject
                                    renderStrategy: Canvas.Threaded
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                    onVisibleChanged: if (visible) requestPaint()
                                    Component.onCompleted: requestPaint()
                                    onPaint: {
                                        var ctx = getContext("2d")
                                        ctx.reset()
                                        ctx.clearRect(0, 0, width, height)
                                        var spec = modelData.metadata.custom_path || {}
                                        var paths = spec.paths || []
                                        for (var p = 0; p < paths.length; ++p) {
                                            var path = paths[p]
                                            var sourceW = Math.max(0.0001, Number(path.width || spec.width || 1))
                                            var sourceH = Math.max(0.0001, Number(path.height || spec.height || 1))
                                            var sx = width / sourceW
                                            var sy = height / sourceH
                                            ctx.beginPath()
                                            var commands = path.commands || []
                                            for (var c = 0; c < commands.length; ++c) {
                                                var command = commands[c]
                                                var pts = command.points || []
                                                if (command.op === "M" && pts.length)
                                                    ctx.moveTo(Number(pts[0][0]) * sx, Number(pts[0][1]) * sy)
                                                else if (command.op === "L" && pts.length)
                                                    ctx.lineTo(Number(pts[0][0]) * sx, Number(pts[0][1]) * sy)
                                                else if (command.op === "C" && pts.length >= 3)
                                                    ctx.bezierCurveTo(Number(pts[0][0]) * sx, Number(pts[0][1]) * sy, Number(pts[1][0]) * sx, Number(pts[1][1]) * sy, Number(pts[2][0]) * sx, Number(pts[2][1]) * sy)
                                                else if (command.op === "Q" && pts.length >= 2)
                                                    ctx.quadraticCurveTo(Number(pts[0][0]) * sx, Number(pts[0][1]) * sy, Number(pts[1][0]) * sx, Number(pts[1][1]) * sy)
                                                else if (command.op === "Z")
                                                    ctx.closePath()
                                            }
                                            var fill = String(modelData.style.fill || "transparent")
                                            if (fill !== "transparent" && fill !== "none" && fill !== "") {
                                                ctx.fillStyle = fill
                                                ctx.fill()
                                            }
                                            var strokeWidth = Number(modelData.style.stroke_width || 0) * zoom
                                            var stroke = String(modelData.style.stroke || "transparent")
                                            if (strokeWidth > 0 && stroke !== "transparent" && stroke !== "none" && stroke !== "") {
                                                ctx.lineWidth = strokeWidth
                                                ctx.strokeStyle = stroke
                                                ctx.stroke()
                                            }
                                        }
                                    }
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
                                    property bool fitTextInside: !!modelData.style.fit_inside_box || String(modelData.style.semantic_fit_policy || "").toLowerCase() === "overflow_only"
                                    anchors.fill: parent
                                    anchors.leftMargin: textInset(modelData.style, "left")
                                    anchors.topMargin: textInset(modelData.style, "top")
                                    anchors.rightMargin: textInset(modelData.style, "right")
                                    anchors.bottomMargin: textInset(modelData.style, "bottom")
                                    visible: modelData.kind === "text"
                                    clip: true
                                    text: modelData.text || ""
                                    color: modelData.style.color || "#111827"
                                    font.family: modelData.style.font_family || "Segoe UI"
                                    font.pixelSize: Math.max(4, Number(modelData.style.font_size || 20) * (String(modelData.style.font_size_unit || "pt") === "pt" ? 1.333333 : 1) * zoom)
                                    font.bold: Number(modelData.style.font_weight || 400) >= 700
                                    font.italic: !!modelData.style.italic
                                    font.letterSpacing: Number(modelData.style.letter_spacing || 0) * zoom
                                    horizontalAlignment: modelData.style.align === "left" ? Text.AlignLeft : modelData.style.align === "right" ? Text.AlignRight : Text.AlignHCenter
                                    verticalAlignment: modelData.style.v_align === "top" ? Text.AlignTop : modelData.style.v_align === "bottom" ? Text.AlignBottom : Text.AlignVCenter
                                    wrapMode: modelData.style.nowrap ? Text.NoWrap : Text.WordWrap
                                    maximumLineCount: 2147483647
                                    fontSizeMode: fitTextInside ? Text.Fit : Text.FixedSize
                                    minimumPixelSize: Math.max(1, 4 * zoom)
                                    elide: fitTextInside ? Text.ElideNone : (modelData.style.nowrap ? Text.ElideNone : Text.ElideRight)
                                    lineHeightMode: textLineHeightMode(modelData.style)
                                    lineHeight: textLineHeight(modelData.style)
                                }
                                Image {
                                    id: nodeImage
                                    anchors.fill: parent
                                    visible: modelData.kind === "image" || modelData.kind === "background"
                                    source: imageSource(modelData)
                                    fillMode: modelData.style.fit === "cover" ? Image.PreserveAspectCrop : modelData.style.fit === "fill" ? Image.Stretch : Image.PreserveAspectFit
                                    horizontalAlignment: Image.AlignHCenter
                                    verticalAlignment: Image.AlignVCenter
                                    mirror: !!modelData.style.flip_x
                                    mirrorVertically: !!modelData.style.flip_y
                                    clip: fillMode === Image.PreserveAspectCrop
                                    asynchronous: true
                                    cache: true
                                    mipmap: true
                                    smooth: true
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    acceptedButtons: Qt.LeftButton
                                    drag.target: window.manualItemSlotForNode(modelData.id) ? null : parent
                                    enabled: !effectiveLocked(modelData)
                                    preventStealing: true
                                    onPressed: {
                                        var manualSlot = window.manualItemSlotForNode(modelData.id)
                                        if (manualSlot) {
                                            selectedSlotId = String(manualSlot.id || "")
                                            return
                                        }
                                        sceneBridge.selectNodeAdvanced(modelData.id, (mouse.modifiers & Qt.ShiftModifier) !== 0, (mouse.modifiers & Qt.ControlModifier) !== 0)
                                    }
                                    onReleased: {
                                        if (window.manualItemSlotForNode(modelData.id))
                                            return
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
                                id: slotOverlay
                                objectName: "smartSlotOverlay-" + String(modelData.id || "")
                                required property var modelData
                                property var bounds: slotBounds(modelData)
                                property var preview_bounds: ({"x": bounds.x, "y": bounds.y, "width": bounds.width, "height": bounds.height})
                                property var pendingPreviewBounds: ({"x": bounds.x, "y": bounds.y, "width": bounds.width, "height": bounds.height})
                                property bool previewActive: false
                                property real lastPreviewAppliedMs: 0
                                property int previewEventCount: 0
                                property int previewUpdateCount: 0
                                property real previewIntervalMs: 16
                                property var displayBounds: previewActive ? preview_bounds : bounds
                                property bool isManualItemSlot: !!(modelData.metadata && modelData.metadata.manual_item_slot)
                                property bool resizePreviewKeepsInteractionGeometry: previewActive && isManualItemSlot && window.itemSlotInteractionKind === "resize"
                                property var interactionBounds: resizePreviewKeepsInteractionGeometry ? bounds : displayBounds
                                property bool slotEditActive: isManualItemSlot || smartSlotEditMode
                                property bool isDropTarget: productDragActive && dragHoverSlotId === modelData.id
                                property bool isSelectedSlot: selectedSlotId === modelData.id
                                property bool isHoveredSlot: hoveredSlotId === modelData.id
                                property bool showSlotOverlay: smartSlotEditMode || smartSlotInspectionMode || productDragActive || isSelectedSlot || isHoveredSlot
                                x: interactionBounds.x * zoom
                                y: interactionBounds.y * zoom
                                width: interactionBounds.width * zoom
                                height: interactionBounds.height * zoom
                                visible: showSlotOverlay && width > 2 && height > 2
                                z: 100000

                                function clampPreview(raw) {
                                    var pageW = page ? Number(page.width || 1) : 1
                                    var pageH = page ? Number(page.height || 1) : 1
                                    var widthValue = Math.max(1, Math.min(Number(raw.width || 1), pageW))
                                    var heightValue = Math.max(1, Math.min(Number(raw.height || 1), pageH))
                                    var xValue = Math.max(0, Math.min(Number(raw.x || 0), Math.max(0, pageW - widthValue)))
                                    var yValue = Math.max(0, Math.min(Number(raw.y || 0), Math.max(0, pageH - heightValue)))
                                    return {"x": xValue, "y": yValue, "width": widthValue, "height": heightValue}
                                }

                                function snapPreview(raw) {
                                    var value = clampPreview(raw)
                                    if (!smartSlotSnap || !scene.editor || !scene.editor.snap)
                                        return value
                                    var step = Math.max(0, Number(scene.editor.snap.grid_spacing || 0))
                                    if (step <= 0)
                                        return value
                                    var left = Math.round(value.x / step) * step
                                    var top = Math.round(value.y / step) * step
                                    var right = Math.round((value.x + value.width) / step) * step
                                    var bottom = Math.round((value.y + value.height) / step) * step
                                    return clampPreview({
                                        "x": left,
                                        "y": top,
                                        "width": Math.max(1, right - left),
                                        "height": Math.max(1, bottom - top)
                                    })
                                }

                                function beginPreview(raw, kind) {
                                    var value = snapPreview(raw)
                                    previewActive = true
                                    pendingPreviewBounds = value
                                    preview_bounds = value
                                    lastPreviewAppliedMs = Date.now()
                                    previewEventCount = 0
                                    previewUpdateCount = 0
                                    window.smartSlotInteractionKind = String(kind || "")
                                    if (isManualItemSlot) {
                                        window.itemSlotPreviewActive = true
                                        window.itemSlotPreviewSlotId = String(modelData.id || "")
                                        window.itemSlotPreviewStartBounds = value
                                        window.itemSlotPreviewBounds = value
                                        window.itemSlotInteractionKind = String(kind || "")
                                    }
                                }

                                function queuePreview(raw, force) {
                                    if (!previewActive)
                                        return
                                    pendingPreviewBounds = snapPreview(raw)
                                    previewEventCount += 1
                                    if (isManualItemSlot)
                                        window.itemSlotPreviewEvents += 1
                                    else
                                        window.smartSlotPreviewEvents += 1
                                    var now = Date.now()
                                    if (force || lastPreviewAppliedMs <= 0 || now - lastPreviewAppliedMs >= previewIntervalMs) {
                                        applyPendingPreview()
                                    } else if (!previewTimer.running) {
                                        previewTimer.start()
                                    }
                                }

                                function applyPendingPreview() {
                                    if (!previewActive)
                                        return
                                    preview_bounds = pendingPreviewBounds
                                    lastPreviewAppliedMs = Date.now()
                                    previewUpdateCount += 1
                                    if (isManualItemSlot) {
                                        window.itemSlotPreviewUpdates += 1
                                        window.itemSlotPreviewBounds = preview_bounds
                                    } else {
                                        window.smartSlotPreviewUpdates += 1
                                    }
                                }

                                function commitPreview(raw, kind) {
                                    if (!previewActive)
                                        return
                                    queuePreview(raw, true)
                                    var finalBounds = preview_bounds
                                    var started = Date.now()
                                    var commandName = isManualItemSlot ? "commit_item_slot_bounds" : "adjust_smart_slot"
                                    sceneBridge.dispatch(JSON.stringify({
                                        "name":commandName,
                                        "slot_id":slotOverlay.modelData.id,
                                        "x":finalBounds.x,
                                        "y":finalBounds.y,
                                        "width":finalBounds.width,
                                        "height":finalBounds.height,
                                        "snap":smartSlotSnap
                                    }))
                                    if (isManualItemSlot) {
                                        window.itemSlotBackendCommits += 1
                                        window.itemSlotInteractionKind = String(kind || "")
                                        window.itemSlotPreviewActive = false
                                        window.itemSlotPreviewSlotId = ""
                                    } else {
                                        window.smartSlotLastCommitMs = Math.max(0, Date.now() - started)
                                        window.smartSlotInteractionKind = String(kind || "")
                                    }
                                    previewActive = false
                                    previewTimer.stop()
                                }

                                Timer {
                                    id: previewTimer
                                    interval: 16
                                    repeat: false
                                    onTriggered: slotOverlay.applyPendingPreview()
                                }

                                Rectangle {
                                    objectName: "smartSlotVisualFrame-" + String(slotOverlay.modelData.id || "")
                                    x: slotOverlay.resizePreviewKeepsInteractionGeometry ? (slotOverlay.displayBounds.x - slotOverlay.interactionBounds.x) * zoom : 0
                                    y: slotOverlay.resizePreviewKeepsInteractionGeometry ? (slotOverlay.displayBounds.y - slotOverlay.interactionBounds.y) * zoom : 0
                                    width: slotOverlay.resizePreviewKeepsInteractionGeometry ? Math.max(1, slotOverlay.displayBounds.width * zoom) : parent.width
                                    height: slotOverlay.resizePreviewKeepsInteractionGeometry ? Math.max(1, slotOverlay.displayBounds.height * zoom) : parent.height
                                    color: isDropTarget ? "#16A34A2A" : (isSelectedSlot ? "#6248F711" : (productDragActive ? "#6248F708" : "transparent"))
                                    border.width: isDropTarget ? 3 : (isSelectedSlot ? 2 : 1)
                                    border.color: isDropTarget ? theme.dropTarget : (isSelectedSlot ? theme.selection : "#6248F755")
                                    radius: 5
                                }
                                Label {
                                    x: 4; y: 4
                                    text: isDropTarget ? "SOLTAR PRODUTO AQUI" : ((modelData.metadata && modelData.metadata.display_label) ? modelData.metadata.display_label : (modelData.name || "Smart Slot"))
                                    color: "white"
                                    font.bold: true
                                    font.pixelSize: 9
                                    padding: 3
                                    background: Rectangle { color: isDropTarget ? theme.dropTarget : (isSelectedSlot ? theme.selection : "#64748BAA"); radius: 3 }
                                }
                                MouseArea {
                                    id: slotMoveArea
                                    objectName: "smartSlotMoveArea-" + String(slotOverlay.modelData.id || "")
                                    anchors.fill: parent
                                    acceptedButtons: Qt.LeftButton
                                    hoverEnabled: true
                                    preventStealing: slotOverlay.slotEditActive
                                    property real startGlobalX: 0
                                    property real startGlobalY: 0
                                    property var startBounds: ({"x":0,"y":0,"width":1,"height":1})
                                    onEntered: hoveredSlotId = slotOverlay.modelData.id
                                    onExited: if (hoveredSlotId === slotOverlay.modelData.id) hoveredSlotId = ""
                                    onPressed: {
                                        selectedSlotId = slotOverlay.modelData.id
                                        if (!slotOverlay.slotEditActive)
                                            return
                                        var point = mapToItem(sheet, mouse.x, mouse.y)
                                        startGlobalX = point.x / zoom
                                        startGlobalY = point.y / zoom
                                        startBounds = {"x":slotOverlay.bounds.x,"y":slotOverlay.bounds.y,"width":slotOverlay.bounds.width,"height":slotOverlay.bounds.height}
                                        slotOverlay.beginPreview(startBounds, "move")
                                    }
                                    onClicked: selectedSlotId = slotOverlay.modelData.id
                                    onPositionChanged: {
                                        if (!pressed || !slotOverlay.slotEditActive || !slotOverlay.previewActive)
                                            return
                                        var point = mapToItem(sheet, mouse.x, mouse.y)
                                        var dx = point.x / zoom - startGlobalX
                                        var dy = point.y / zoom - startGlobalY
                                        slotOverlay.queuePreview({
                                            "x":startBounds.x + dx,
                                            "y":startBounds.y + dy,
                                            "width":startBounds.width,
                                            "height":startBounds.height
                                        }, false)
                                    }
                                    onReleased: {
                                        if (!slotOverlay.slotEditActive || !slotOverlay.previewActive)
                                            return
                                        var point = mapToItem(sheet, mouse.x, mouse.y)
                                        var dx = point.x / zoom - startGlobalX
                                        var dy = point.y / zoom - startGlobalY
                                        slotOverlay.commitPreview({
                                            "x":startBounds.x + dx,
                                            "y":startBounds.y + dy,
                                            "width":startBounds.width,
                                            "height":startBounds.height
                                        }, "move")
                                    }
                                    onCanceled: {
                                        if (slotOverlay.isManualItemSlot) {
                                            window.itemSlotPreviewActive = false
                                            window.itemSlotPreviewSlotId = ""
                                        }
                                        slotOverlay.previewActive = false
                                        previewTimer.stop()
                                    }
                                }
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
                                    delegate: MouseArea {
                                        required property var modelData
                                        objectName: "smartSlotResizeArea-" + String(modelData.dir) + "-" + String(slotOverlay.modelData.id || "")
                                        visible: slotOverlay.slotEditActive && slotOverlay.isSelectedSlot
                                        property real visualSize: 11
                                        property real desiredVisualX: (slotOverlay.displayBounds.x - slotOverlay.interactionBounds.x) * zoom
                                                                      + modelData.fx * slotOverlay.displayBounds.width * zoom
                                                                      - visualSize / 2
                                        property real desiredVisualY: (slotOverlay.displayBounds.y - slotOverlay.interactionBounds.y) * zoom
                                                                      + modelData.fy * slotOverlay.displayBounds.height * zoom
                                                                      - visualSize / 2
                                        width: 18
                                        height: 18
                                        x: Math.max(0, Math.min(Math.max(0, slotOverlay.width - width), modelData.fx * slotOverlay.width - width / 2))
                                        y: Math.max(0, Math.min(Math.max(0, slotOverlay.height - height), modelData.fy * slotOverlay.height - height / 2))
                                        z: 10
                                        acceptedButtons: Qt.LeftButton
                                        cursorShape: modelData.cursor
                                        preventStealing: true
                                        Item {
                                            objectName: "smartSlotHandle-" + String(modelData.dir) + "-" + String(slotOverlay.modelData.id || "")
                                            anchors.fill: parent
                                        }
                                        Rectangle {
                                            objectName: "smartSlotVisualHandle-" + String(modelData.dir) + "-" + String(slotOverlay.modelData.id || "")
                                            visible: parent.visible
                                            x: parent.desiredVisualX - parent.x
                                            y: parent.desiredVisualY - parent.y
                                            width: parent.visualSize
                                            height: parent.visualSize
                                            radius: 2
                                            color: "white"
                                            border.width: 2
                                            border.color: theme.selection
                                        }
                                        property real startGlobalX: 0
                                        property real startGlobalY: 0
                                        property real startX: 0
                                        property real startY: 0
                                        property real startW: 0
                                        property real startH: 0
                                        function resizedBounds(px, py, modifiers) {
                                            var dx = px / zoom - startGlobalX
                                            var dy = py / zoom - startGlobalY
                                            var nx = startX
                                            var ny = startY
                                            var nw = startW
                                            var nh = startH
                                            if (modelData.dir.indexOf("w") >= 0) { nx += dx; nw -= dx }
                                            if (modelData.dir.indexOf("e") >= 0) nw += dx
                                            if (modelData.dir.indexOf("n") >= 0) { ny += dy; nh -= dy }
                                            if (modelData.dir.indexOf("s") >= 0) nh += dy
                                            if (nw < 1) { if (modelData.dir.indexOf("w") >= 0) nx -= (1 - nw); nw = 1 }
                                            if (nh < 1) { if (modelData.dir.indexOf("n") >= 0) ny -= (1 - nh); nh = 1 }
                                            if (slotOverlay.isManualItemSlot && (modifiers & Qt.ShiftModifier)) {
                                                var aspect = Math.max(0.000001, startW) / Math.max(0.000001, startH)
                                                var hasH = modelData.dir.indexOf("e") >= 0 || modelData.dir.indexOf("w") >= 0
                                                var hasV = modelData.dir.indexOf("n") >= 0 || modelData.dir.indexOf("s") >= 0
                                                var targetW = nw
                                                var targetH = nh
                                                if (hasH && hasV) {
                                                    var relW = Math.abs(nw - startW) / Math.max(1, startW)
                                                    var relH = Math.abs(nh - startH) / Math.max(1, startH)
                                                    if (relW >= relH)
                                                        targetH = Math.max(1, targetW / aspect)
                                                    else
                                                        targetW = Math.max(1, targetH * aspect)
                                                } else if (hasH) {
                                                    targetH = Math.max(1, targetW / aspect)
                                                } else if (hasV) {
                                                    targetW = Math.max(1, targetH * aspect)
                                                }
                                                if (modelData.dir.indexOf("w") >= 0)
                                                    nx = startX + startW - targetW
                                                if (modelData.dir.indexOf("n") >= 0)
                                                    ny = startY + startH - targetH
                                                nw = targetW
                                                nh = targetH
                                            }
                                            return {"x":nx,"y":ny,"width":nw,"height":nh}
                                        }
                                        onPressed: {
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            startGlobalX = point.x / zoom
                                            startGlobalY = point.y / zoom
                                            startX = slotOverlay.displayBounds.x
                                            startY = slotOverlay.displayBounds.y
                                            startW = slotOverlay.displayBounds.width
                                            startH = slotOverlay.displayBounds.height
                                            slotOverlay.beginPreview({"x":startX,"y":startY,"width":startW,"height":startH}, "resize")
                                        }
                                        onPositionChanged: {
                                            if (!pressed || !slotOverlay.previewActive)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            slotOverlay.queuePreview(resizedBounds(point.x, point.y, mouse.modifiers), false)
                                        }
                                        onReleased: {
                                            if (!slotOverlay.previewActive)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            slotOverlay.commitPreview(resizedBounds(point.x, point.y, mouse.modifiers), "resize")
                                        }
                                        onCanceled: {
                                            if (slotOverlay.isManualItemSlot) {
                                                window.itemSlotPreviewActive = false
                                                window.itemSlotPreviewSlotId = ""
                                            }
                                            slotOverlay.previewActive = false
                                            previewTimer.stop()
                                        }
                                    }
                                }
                            }
                        }

                        Item {
                            id: selectionOverlay
                            visible: anchorNode && page && effectiveVisible(anchorNode) && !window.manualItemSlotForNode(anchorNode.id)
                            x: visible ? anchorNode.transform.x * zoom : 0
                            y: visible ? anchorNode.transform.y * zoom : 0
                            width: visible ? Math.max(1, anchorNode.transform.width * zoom) : 1
                            height: visible ? Math.max(1, anchorNode.transform.height * zoom) : 1
                            rotation: visible ? Number(anchorNode.transform.rotation || 0) : 0
                            z: 200000

                            Rectangle { anchors.fill: parent; color: "transparent"; border.width: 2; border.color: theme.selection }
                            Rectangle { x: parent.width / 2; y: -30; width: 1; height: 30; color: theme.selection }
                            Rectangle {
                                id: rotateHandle
                                width: 13
                                height: 13
                                radius: 7
                                x: parent.width / 2 - 6.5
                                y: -42
                                color: "white"
                                border.width: 2
                                border.color: theme.selection
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.CrossCursor
                                    enabled: !!anchorNode && !effectiveLocked(anchorNode)
                                    preventStealing: true
                                    property real pressAngle: 0
                                    property real startRotation: 0
                                    function angleAt(px, py) {
                                        var dx = rotateHandle.x + px - selectionOverlay.width / 2
                                        var dy = rotateHandle.y + py - selectionOverlay.height / 2
                                        return Math.atan2(dy, dx) * 180 / Math.PI + 90
                                    }
                                    onPressed: {
                                        pressAngle = angleAt(mouse.x, mouse.y)
                                        startRotation = anchorNode ? Number(anchorNode.transform.rotation || 0) : 0
                                    }
                                    onReleased: {
                                        if (!anchorNode) return
                                        var delta = angleAt(mouse.x, mouse.y) - pressAngle
                                        while (delta > 180) delta -= 360
                                        while (delta < -180) delta += 360
                                        var target = startRotation + delta
                                        sceneBridge.dispatch(JSON.stringify({"name":"rotate","angle":target,"snap":(mouse.modifiers & Qt.ShiftModifier) !== 0 ? 15 : null}))
                                    }
                                }
                            }

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
                                    border.color: theme.selection
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

            Rectangle {
                id: zoomBar
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 18
                width: window.tightUi ? 252 : 318
                height: 42
                radius: theme.radius
                color: "#FFFFFFF5"
                border.width: 1
                border.color: theme.border
                z: 399999
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 6
                    ToolButton { text: "−"; onClicked: window.zoom = Math.max(0.12, window.zoom / 1.1) }
                    Slider { Layout.fillWidth: true; from: 0.12; to: 3.5; value: window.zoom; onMoved: window.zoom = value }
                    Label { text: Math.round(window.zoom * 100) + "%"; color: theme.text; font.pixelSize: theme.fontSmall; font.bold: true; Layout.preferredWidth: 42; horizontalAlignment: Text.AlignRight }
                    ToolButton { text: "+"; onClicked: window.zoom = Math.min(3.5, window.zoom * 1.1) }
                    Button { visible: !window.tightUi; text: "Ajustar"; onClicked: fitToViewport() }
                }
            }
        }

        Rectangle {
            id: inspector
            SplitView.preferredWidth: window.studioInspectorWidth
            SplitView.minimumWidth: 270
            SplitView.maximumWidth: 390
            color: theme.surface
            Rectangle { anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 1; color: theme.border }

            ScrollView {
                anchors.fill: parent
                clip: true
                ScrollBar.vertical.policy: ScrollBar.AsNeeded
                ColumnLayout {
                    width: Math.max(246, parent.width - 24)
                    x: 12
                    y: 12
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: "Propriedades"; color: theme.text; font.pixelSize: theme.fontTitle; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Rectangle { implicitWidth: 44; implicitHeight: 22; radius: theme.radiusPill; color: theme.primarySoft; Label { anchors.centerIn: parent; text: "G2"; color: theme.primary; font.pixelSize: 9; font.bold: true } }
                    }

                    InspectorSection {
                        theme: theme
                        title: "Seleção"
                        Label { id: inspectorName; Layout.fillWidth: true; text: "Nada selecionado"; color: theme.text; font.pixelSize: theme.fontSmall; font.bold: true; elide: Text.ElideRight }
                        Label { Layout.fillWidth: true; text: selectedSlotId ? ("Slot: " + selectedSlotId) : sceneBridge.status; color: selectedSlotId ? theme.primary : theme.textMuted; font.pixelSize: theme.fontTiny; elide: Text.ElideMiddle }
                    }

                    InspectorSection {
                        theme: theme
                        title: "Layout e posicionamento"
                        GridLayout {
                            columns: 2
                            columnSpacing: 8
                            rowSpacing: 7
                            Layout.fillWidth: true
                            Label { text: "X"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                            TextField { id: xField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Y"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                            TextField { id: yField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Largura"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                            TextField { id: wField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Altura"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                            TextField { id: hField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                            Label { text: "Rotação"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
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
                        Label { text: "Opacidade"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                        Slider { id: opacityField; from: 0; to: 1; stepSize: 0.01; value: 1; Layout.fillWidth: true; onMoved: if (anchorNode) sceneBridge.dispatch(JSON.stringify({"name":"opacity","value":value})) }
                    }

                    InspectorSection {
                        theme: theme
                        title: "Texto"
                        visible: anchorNode && anchorNode.kind === "text"
                        TextArea { id: textEditor; Layout.fillWidth: true; Layout.preferredHeight: 86; wrapMode: TextEdit.Wrap }
                        Button { text: "Aplicar texto"; Layout.fillWidth: true; onClicked: if (anchorNode) sceneBridge.editText(anchorNode.id, textEditor.text) }
                    }

                    InspectorSection {
                        theme: theme
                        title: "Organizar"
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
                            Button { text: "Ocultar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"hide","value":true}') }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button { text: "▲ Frente"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"front"}') }
                            Button { text: "▼ Fundo"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"layer","mode":"back"}') }
                        }
                    }

                    InspectorSection {
                        theme: theme
                        title: "Estado do editor"
                        Label { Layout.fillWidth: true; text: "Grid " + (showGrid ? "ativo" : "oculto") + " · Réguas " + (showRulers ? "ativas" : "ocultas") + " · Zoom " + Math.round(zoom * 100) + "%"; color: theme.primary; font.pixelSize: theme.fontSmall; wrapMode: Text.WordWrap }
                        Label { Layout.fillWidth: true; text: "Qt Quick / RHI · preview local de ItemSlot preservado"; color: theme.textMuted; font.pixelSize: theme.fontTiny; wrapMode: Text.WordWrap }
                    }
                    Item { Layout.preferredHeight: 12 }
                }
            }
        }
    }

    Rectangle {
        id: pageFooter
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 52
        color: "#FFFFFFF7"
        border.color: theme.border
        z: 350000
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: window.studioLeftDockWidth + 12
            anchors.rightMargin: window.studioInspectorWidth + 12
            spacing: 6
            Label { text: "Páginas"; font.bold: true; color: theme.text; font.pixelSize: theme.fontSmall }
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
            Label { visible: !window.tightUi; text: productDragActive ? (dragHoverSlotId ? "Solte para aplicar o produto" : "Arraste sobre um card") : ("Snap ✓ · Grid " + (showGrid ? "✓" : "—") + " · Réguas " + (showRulers ? "✓" : "—")); color: productDragActive ? (dragHoverSlotId ? theme.dropTarget : theme.primary) : theme.textMuted; font.pixelSize: theme.fontTiny }
        }
    }

    Rectangle {
        id: productDragGhost
        visible: productDragActive && !!draggedProduct
        x: productDragX - width / 2
        y: productDragY - height / 2
        width: 264
        height: 76
        z: 1000000
        radius: theme.radiusLarge
        color: "#FFFFFFFA"
        border.width: 2
        border.color: dragHoverSlotId ? theme.dropTarget : theme.primary
        opacity: 0.98

        RowLayout {
            anchors.fill: parent
            anchors.margins: 9
            spacing: 9
            Rectangle {
                Layout.preferredWidth: 54
                Layout.preferredHeight: 54
                radius: 8
                color: theme.surfaceMuted
                border.color: theme.border
                clip: true
                Image {
                    anchors.fill: parent
                    anchors.margins: 3
                    source: localSource(draggedProduct ? (draggedProduct.image_path || draggedProduct.image || "") : "")
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Label { Layout.fillWidth: true; text: productLabel(draggedProduct); color: theme.text; font.bold: true; font.pixelSize: theme.fontBody; elide: Text.ElideRight }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 28
                    radius: theme.radiusPill
                    color: dragHoverSlotId ? theme.success : theme.primary
                    Label { anchors.centerIn: parent; text: dragHoverSlotId ? "Solte para aplicar o produto" : "Arraste o produto para o encarte"; color: "white"; font.bold: true; font.pixelSize: theme.fontTiny }
                }
            }
        }
    }
}
