import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: window
    width: 1760
    height: 1020
    minimumWidth: 1180
    minimumHeight: 760
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
    property var anchorNode: selectedNode()
    property var draggedProduct: null
    property bool productDragActive: false
    property real productDragX: 0
    property real productDragY: 0
    property string dragHoverSlotId: ""
    property string productSearch: ""
    property string productCategory: "Todos"
    property string leftSection: "Produtos"
    property int inspectorTab: 0
    readonly property bool compactUi: width < 1500
    readonly property bool tightUi: width < 1320
    readonly property real studioLeftDockWidth: tightUi ? 310 : (compactUi ? 354 : 426)
    readonly property real studioInspectorWidth: tightUi ? 286 : (compactUi ? 320 : theme.inspectorWidth)

    function activePage() {
        if (!scene.pages || !scene.pages.length)
            return null
        for (var i = 0; i < scene.pages.length; ++i)
            if (scene.pages[i].id === scene.active_page_id)
                return scene.pages[i]
        return scene.pages[0]
    }

    function activePageIndex() {
        if (!scene.pages)
            return 0
        for (var i = 0; i < scene.pages.length; ++i)
            if (scene.pages[i].id === scene.active_page_id)
                return i
        return 0
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

    function selectedSlot() {
        var available = slots()
        for (var i = 0; i < available.length; ++i)
            if (String(available[i].id || "") === String(selectedSlotId || ""))
                return available[i]
        return null
    }

    function slotProductId(slot) {
        if (!slot)
            return ""
        var metadata = slot.metadata || {}
        var candidates = [
            slot.bound_product_id,
            slot.product_id,
            metadata.bound_product_id,
            metadata.product_id,
            metadata.current_product_id,
            metadata.bound_product && metadata.bound_product.id,
            metadata.product && metadata.product.id
        ]
        for (var i = 0; i < candidates.length; ++i)
            if (candidates[i] !== undefined && candidates[i] !== null && String(candidates[i]) !== "")
                return String(candidates[i])
        var roles = slot.node_by_role || {}
        for (var key in roles) {
            var node = page && page.nodes ? page.nodes[String(roles[key])] : null
            if (!node)
                continue
            var nodeMetadata = node.metadata || {}
            var nodeId = nodeMetadata.bound_product_id || nodeMetadata.product_id || ""
            if (nodeId)
                return String(nodeId)
        }
        return ""
    }

    function selectedProduct() {
        var slot = selectedSlot()
        var productId = slotProductId(slot)
        if (!productId)
            return null
        var available = products()
        for (var i = 0; i < available.length; ++i) {
            var id = String(available[i].id || available[i].product_id || "")
            if (id === productId)
                return available[i]
        }
        return null
    }

    function selectedSlotImageNode() {
        var slot = selectedSlot()
        if (!slot || !page)
            return null
        var roles = slot.node_by_role || {}
        var imageId = roles.image || roles.IMAGE || roles.product_image || ""
        if (imageId && page.nodes[imageId])
            return page.nodes[imageId]
        var metadata = slot.metadata || {}
        imageId = metadata.image_node_id || ""
        return imageId && page.nodes[imageId] ? page.nodes[imageId] : null
    }

    function slotPresetLabel(slot) {
        if (!slot)
            return "—"
        var metadata = slot.metadata || {}
        return String(metadata.preset_id || metadata.item_slot_preset_id || metadata.preset || metadata.source || slot.name || "Smart Slot")
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

    function productImageSource(product) {
        if (!product)
            return ""
        return localSource(product.image_path || product.image || product.image_url || product.source || "")
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

    function productPrice(product, secondary) {
        if (!product)
            return "—"
        var value = secondary ? (product.promotional_price !== undefined ? product.promotional_price : product.secondary_price) : product.price
        if (value === undefined || value === null || value === "")
            return "—"
        return String(value).replace(".", ",")
    }

    function priceInteger(product, secondary) {
        var raw = productPrice(product, secondary)
        if (raw === "—")
            return "—"
        var cleaned = raw.replace("R$", "").trim()
        var comma = cleaned.indexOf(",")
        return comma >= 0 ? cleaned.substring(0, comma) : cleaned
    }

    function priceDecimal(product, secondary) {
        var raw = productPrice(product, secondary)
        if (raw === "—")
            return "—"
        var cleaned = raw.replace("R$", "").trim()
        var comma = cleaned.indexOf(",")
        return comma >= 0 ? "," + cleaned.substring(comma + 1) : ",00"
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
        var usableWidth = Math.max(220, viewport.width - 180)
        var usableHeight = Math.max(220, viewport.height - 150)
        var target = Math.min(usableWidth / Math.max(1, page.width), usableHeight / Math.max(1, page.height))
        zoom = Math.max(0.12, Math.min(3.5, target))
    }

    function syncInspector() {
        var node = selectedNode()
        anchorNode = node
        if (!node) {
            inspectorName.text = selectedSlot() ? String(selectedSlot().name || "Smart Slot") : "Nada selecionado"
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
        Qt.callLater(fitToViewport)
    }

    Shortcut { sequence: StandardKey.Undo; onActivated: sceneBridge.undo() }
    Shortcut { sequence: StandardKey.Redo; onActivated: sceneBridge.redo() }
    Shortcut { sequence: StandardKey.Delete; onActivated: sceneBridge.dispatch('{"name":"delete"}') }
    Shortcut { sequence: "Ctrl+D"; onActivated: sceneBridge.dispatch('{"name":"duplicate"}') }
    Shortcut { sequence: "Ctrl+G"; onActivated: sceneBridge.dispatch('{"name":"group"}') }
    Shortcut { sequence: "Ctrl+Shift+G"; onActivated: sceneBridge.dispatch('{"name":"ungroup"}') }
    Shortcut { sequence: "G"; onActivated: showGrid = !showGrid }

    header: Item {
        implicitHeight: theme.topHeaderHeight

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: window.studioLeftDockWidth
            color: theme.navDeep
        }

        Rectangle {
            anchors.left: parent.left
            anchors.leftMargin: window.studioLeftDockWidth
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#6444F5" }
                GradientStop { position: 0.55; color: "#4475F3" }
                GradientStop { position: 1.0; color: "#16C6C0" }
            }
        }

        RowLayout {
            anchors.fill: parent
            spacing: 0

            Item {
                Layout.preferredWidth: window.studioLeftDockWidth
                Layout.fillHeight: true
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 12
                    spacing: 9
                    Rectangle {
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        radius: 8
                        color: "#FFFFFF0F"
                        border.width: 1
                        border.color: "#FFFFFF15"
                        Label { anchors.centerIn: parent; text: "▰"; color: "#C5B8FF"; font.pixelSize: 18; font.bold: true }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "Studio de Encartes"
                        color: "#E8E4FF"
                        font.pixelSize: 17
                        font.bold: true
                        elide: Text.ElideRight
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 14
                Layout.leftMargin: 20

                Repeater {
                    model: ["Arquivo", "Editar", "Ver", "Inserir", "Formato", "Página", "Ajuda"]
                    delegate: Label {
                        required property var modelData
                        visible: !window.tightUi || index < 4
                        text: modelData
                        color: "#FFFFFF"
                        font.pixelSize: 11
                        font.bold: false
                        opacity: 0.96
                    }
                }

                Item { Layout.fillWidth: true }
                Label {
                    Layout.maximumWidth: window.compactUi ? 230 : 370
                    text: scene.name || "Novo Projeto SR"
                    color: "#FFFFFF"
                    font.pixelSize: 11
                    font.bold: true
                    elide: Text.ElideMiddle
                    horizontalAlignment: Text.AlignRight
                }
                Label {
                    visible: !window.tightUi
                    Layout.maximumWidth: 190
                    text: sceneBridge.status
                    color: "#E7FFFF"
                    opacity: 0.9
                    font.pixelSize: 9
                    elide: Text.ElideRight
                }
                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    radius: 14
                    color: "#FFFFFF22"
                    Label { anchors.centerIn: parent; text: "?"; color: "white"; font.bold: true }
                }
                Rectangle {
                    Layout.preferredWidth: 30
                    Layout.preferredHeight: 30
                    radius: 15
                    color: "#FFFFFF"
                    Label { anchors.centerIn: parent; text: "SR"; color: theme.primary; font.pixelSize: 9; font.bold: true }
                }
                Item { Layout.preferredWidth: 12 }
            }
        }
    }

    SplitView {
        id: studioSplit
        anchors.fill: parent
        anchors.topMargin: theme.toolBarHeight
        orientation: Qt.Horizontal

        Rectangle {
            id: leftDock
            SplitView.preferredWidth: window.studioLeftDockWidth
            SplitView.minimumWidth: window.tightUi ? 292 : 322
            SplitView.maximumWidth: 470
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
                    id: productsPanel
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: theme.navPanel
                    border.width: 0

                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: 1
                        color: theme.navBorder
                    }

                    StackLayout {
                        anchors.fill: parent
                        currentIndex: window.leftSection === "Produtos" ? 0 : 1

                        ColumnLayout {
                            anchors.margins: window.tightUi ? 10 : 14
                            spacing: 9

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        Label { text: "◈"; color: "#B8A8FF"; font.pixelSize: 18 }
                                        Label { text: "Produtos"; color: theme.navText; font.pixelSize: theme.fontTitle; font.bold: true }
                                    }
                                    Label { text: "Importados da planilha"; color: theme.navMuted; font.pixelSize: theme.fontSmall }
                                }
                                Rectangle {
                                    implicitWidth: productCountText.implicitWidth + 18
                                    implicitHeight: 26
                                    radius: theme.radiusPill
                                    color: "#FFFFFF12"
                                    border.width: 1
                                    border.color: "#FFFFFF12"
                                    Label { id: productCountText; anchors.centerIn: parent; text: products().length + " produtos"; color: "#DCE3FA"; font.pixelSize: 9; font.bold: true }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 7
                                Button {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 38
                                    text: "▣  Importar Planilha"
                                    enabled: false
                                    ToolTip.text: "A importação dinâmica ainda não é exposta pelo SceneBridge; o fluxo existente de abertura XLSX/PPTX foi preservado."
                                    ToolTip.visible: hovered
                                    contentItem: Text {
                                        text: parent.text
                                        color: "#FFFFFF"
                                        font.pixelSize: theme.fontButton
                                        font.bold: true
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    background: Rectangle { radius: theme.radiusSmall; color: theme.success }
                                }
                                Button {
                                    Layout.preferredWidth: window.tightUi ? 72 : 104
                                    Layout.preferredHeight: 38
                                    text: window.tightUi ? "↻" : "↻  Sincronizar"
                                    enabled: false
                                    ToolTip.text: "Sincronização dinâmica não possui ação no host Qt atual."
                                    ToolTip.visible: hovered
                                    contentItem: Text { text: parent.text; color: theme.navText; font.pixelSize: theme.fontSmall; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                    background: Rectangle { radius: theme.radiusSmall; color: "#FFFFFF0D"; border.width: 1; border.color: "#FFFFFF14" }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 7
                                TextField {
                                    id: productSearchField
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
                                Button {
                                    Layout.preferredWidth: window.tightUi ? 38 : 72
                                    Layout.preferredHeight: 34
                                    text: window.tightUi ? "⌁" : "⌁  Filtros"
                                    enabled: false
                                    contentItem: Text { text: parent.text; color: theme.navMuted; font.pixelSize: theme.fontSmall; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                    background: Rectangle { radius: theme.radiusSmall; color: "#FFFFFF0B"; border.width: 1; border.color: "#FFFFFF14" }
                                }
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
                                    width: productList.width - (productList.ScrollBar.vertical && productList.ScrollBar.vertical.visible ? 8 : 2)
                                    theme: theme
                                    productData: modelData
                                    imageSource: productImageSource(modelData)
                                    active: selectedProduct() && String(selectedProduct().id || selectedProduct().product_id || "") === String(modelData.id || modelData.product_id || "")
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
                                    text: products().length === 0 ? "Abra um projeto com produtos importados para preencher esta lista." : "Nenhum produto corresponde aos filtros."
                                    width: Math.max(120, productList.width - 34)
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
                            anchors.margins: 18
                            spacing: 10
                            Label { text: window.leftSection; color: theme.navText; font.pixelSize: theme.fontTitle; font.bold: true }
                            Label {
                                Layout.fillWidth: true
                                text: "A navegação visual está pronta. Esta missão não cria backends novos para esta seção."
                                color: theme.navMuted
                                font.pixelSize: theme.fontSmall
                                wrapMode: Text.WordWrap
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: workspace
            SplitView.fillWidth: true
            SplitView.minimumWidth: 420
            color: theme.workspace

            Rectangle {
                id: workspaceHeader
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 44
                color: "#F8FAFD"
                border.width: 0
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: theme.border }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 16
                    spacing: 8
                    Label { text: "Página " + (activePageIndex() + 1) + " - " + (page ? (page.name || "Encarte") : "Encarte"); color: theme.text; font.pixelSize: 11; font.bold: true }
                    Rectangle { visible: (scene.pages || []).length > 1; implicitWidth: pageCount.implicitWidth + 12; implicitHeight: 22; radius: theme.radiusPill; color: theme.surface; border.width: 1; border.color: theme.border; Label { id: pageCount; anchors.centerIn: parent; text: (scene.pages || []).length + " páginas"; color: theme.textMuted; font.pixelSize: theme.fontTiny } }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: "+  Adicionar página"
                        Layout.preferredHeight: 30
                        onClicked: sceneBridge.dispatch('{"name":"add_page"}')
                        contentItem: Text { text: parent.text; color: theme.text; font.pixelSize: theme.fontSmall; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { radius: theme.radiusSmall; color: theme.surface; border.width: 1; border.color: theme.borderStrong }
                    }
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
                contentWidth: Math.max(width, (page ? page.width : 1080) * zoom + 260)
                contentHeight: Math.max(height, (page ? page.height : 1350) * zoom + 210)

                Item {
                    id: world
                    width: viewport.contentWidth
                    height: viewport.contentHeight

                    Rectangle {
                        id: topRuler
                        visible: showRulers && page
                        x: sheet.x
                        y: sheet.y - 25
                        width: sheet.width
                        height: 23
                        color: theme.ruler
                        border.color: theme.border
                        clip: true
                        Repeater {
                            model: page ? Math.ceil(page.width / gridStep) + 1 : 0
                            delegate: Item {
                                x: index * gridStep * zoom
                                width: 1
                                height: topRuler.height
                                Rectangle { x: 0; y: parent.height - 7; width: 1; height: 7; color: theme.rulerTick }
                                Label { x: 3; y: 1; text: Math.round(index * gridStep); color: theme.rulerTick; font.pixelSize: 7 }
                            }
                        }
                    }

                    Rectangle {
                        id: leftRuler
                        visible: showRulers && page
                        x: sheet.x - 27
                        y: sheet.y
                        width: 25
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
                                Rectangle { x: parent.width - 7; y: 0; width: 7; height: 1; color: theme.rulerTick }
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
                        x: Math.max(80, (world.width - width) / 2)
                        y: 76
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
                                x: modelData.transform.x * zoom
                                y: modelData.transform.y * zoom
                                width: Math.max(1, modelData.transform.width * zoom)
                                height: Math.max(1, modelData.transform.height * zoom)
                                rotation: Number(modelData.transform.rotation || 0)
                                opacity: effectiveOpacity(modelData)
                                visible: modelData.kind !== "group" || isSelected(modelData)

                                Rectangle {
                                    anchors.fill: parent
                                    visible: (modelData.kind === "rect" && !hasCustomPath(modelData)) || modelData.kind === "group"
                                    color: modelData.kind === "group" ? "transparent" : (modelData.style.fill || "transparent")
                                    border.width: modelData.kind === "group" ? 1 : Number(modelData.style.stroke_width || 0) * zoom
                                    border.color: modelData.kind === "group" ? "#6248F766" : (modelData.style.stroke || "transparent")
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
                                property bool isDropTarget: productDragActive && dragHoverSlotId === modelData.id
                                x: bounds.x * zoom
                                y: bounds.y * zoom
                                width: bounds.width * zoom
                                height: bounds.height * zoom
                                visible: width > 2 && height > 2
                                z: 100000
                                Rectangle {
                                    anchors.fill: parent
                                    color: isDropTarget ? "#0EAA782A" : (selectedSlotId === modelData.id ? "#6248F711" : "transparent")
                                    border.width: isDropTarget ? 3 : (selectedSlotId === modelData.id ? 2 : 1)
                                    border.color: isDropTarget ? theme.dropTarget : (selectedSlotId === modelData.id ? theme.selection : "#6248F755")
                                    radius: 5
                                }
                                Label {
                                    x: 4; y: 4
                                    text: isDropTarget ? "SOLTAR PRODUTO AQUI" : (modelData.name || "Smart Slot")
                                    color: "white"
                                    font.bold: true
                                    font.pixelSize: 8
                                    padding: 4
                                    background: Rectangle { color: isDropTarget ? theme.dropTarget : (selectedSlotId === modelData.id ? theme.selection : "#56617DAA"); radius: 4 }
                                }
                                MouseArea { anchors.fill: parent; acceptedButtons: Qt.LeftButton; onClicked: { selectedSlotId = modelData.id; Qt.callLater(syncInspector) } }
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

                            Rectangle { anchors.fill: parent; color: "transparent"; border.width: 2; border.color: theme.selection }
                            Rectangle { x: parent.width / 2; y: -28; width: 1; height: 28; color: theme.selection }
                            Rectangle {
                                id: rotateHandle
                                width: 13
                                height: 13
                                radius: 7
                                x: parent.width / 2 - 6.5
                                y: -40
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
                                    width: 11; height: 11; radius: 3
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
                id: zoomBarShadow
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 15
                width: zoomBar.width
                height: zoomBar.height
                x: zoomBar.x + 3
                y: zoomBar.y + 4
                radius: theme.radius
                color: theme.shadowSoft
                z: 399998
            }
            Rectangle {
                id: zoomBar
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 18
                width: window.tightUi ? 270 : 330
                height: 44
                radius: theme.radius
                color: "#FFFFFFF5"
                border.width: 1
                border.color: theme.border
                z: 399999
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 9
                    anchors.rightMargin: 9
                    spacing: 6
                    ToolButton { text: "−"; onClicked: window.zoom = Math.max(0.12, window.zoom / 1.1) }
                    Slider { Layout.fillWidth: true; from: 0.12; to: 3.5; value: window.zoom; onMoved: window.zoom = value }
                    Label { text: Math.round(window.zoom * 100) + "%"; color: theme.text; font.pixelSize: theme.fontSmall; font.bold: true; Layout.preferredWidth: 42; horizontalAlignment: Text.AlignRight }
                    ToolButton { text: "+"; onClicked: window.zoom = Math.min(3.5, window.zoom * 1.1) }
                    Button {
                        visible: !window.tightUi
                        text: "Ajustar"
                        onClicked: fitToViewport()
                        contentItem: Text { text: parent.text; color: theme.text; font.pixelSize: theme.fontSmall; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { radius: theme.radiusSmall; color: theme.surfaceMuted; border.width: 1; border.color: theme.border }
                    }
                }
            }
        }

        Rectangle {
            id: inspector
            SplitView.preferredWidth: window.studioInspectorWidth
            SplitView.minimumWidth: 270
            SplitView.maximumWidth: 430
            color: theme.surface
            border.width: 0

            Rectangle { anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 1; color: theme.border }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                TabBar {
                    id: inspectorTabs
                    Layout.fillWidth: true
                    Layout.preferredHeight: 46
                    currentIndex: window.inspectorTab
                    onCurrentIndexChanged: window.inspectorTab = currentIndex
                    background: Rectangle { color: theme.surface }
                    Repeater {
                        model: ["PROPRIEDADES", "CAMADAS", "DADOS"]
                        delegate: TabButton {
                            required property var modelData
                            text: modelData
                            contentItem: Text {
                                text: parent.text
                                color: parent.checked ? theme.primary : theme.textMuted
                                font.pixelSize: theme.fontTiny
                                font.bold: parent.checked
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            background: Item {
                                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 2; color: parent.parent.checked ? theme.primary : "transparent" }
                            }
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: inspectorTabs.currentIndex

                    ScrollView {
                        id: propertiesScroll
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                        ColumnLayout {
                            width: Math.max(240, propertiesScroll.availableWidth - 24)
                            x: 12
                            y: 12
                            spacing: 10

                            InspectorSection {
                                theme: theme
                                title: selectedSlot() ? "Slot inteligente selecionado" : "Seleção"

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Rectangle {
                                        Layout.preferredWidth: 44
                                        Layout.preferredHeight: 44
                                        radius: 7
                                        color: theme.surfaceMuted
                                        border.width: 1
                                        border.color: theme.border
                                        clip: true
                                        Image { anchors.fill: parent; anchors.margins: 3; source: productImageSource(selectedProduct()); fillMode: Image.PreserveAspectFit; asynchronous: true }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 1
                                        Label { Layout.fillWidth: true; text: selectedProduct() ? productLabel(selectedProduct()).toUpperCase() : (selectedSlot() ? String(selectedSlot().name || "SMART SLOT").toUpperCase() : "NADA SELECIONADO"); color: theme.text; font.pixelSize: theme.fontSmall; font.bold: true; elide: Text.ElideRight }
                                        Label { Layout.fillWidth: true; text: selectedSlot() ? ("ID: " + String(selectedSlot().id || "—")) : (anchorNode ? String(anchorNode.id || "") : ""); color: theme.textMuted; font.pixelSize: theme.fontTiny; elide: Text.ElideMiddle }
                                        Label { Layout.fillWidth: true; text: selectedSlot() ? ("Preset: " + slotPresetLabel(selectedSlot())) : ""; color: theme.primary; font.pixelSize: theme.fontTiny; elide: Text.ElideRight }
                                    }
                                    Rectangle {
                                        visible: !!selectedSlot()
                                        implicitWidth: activeStatus.implicitWidth + 12
                                        implicitHeight: 22
                                        radius: theme.radiusPill
                                        color: theme.successSoft
                                        Label { id: activeStatus; anchors.centerIn: parent; text: "• Ativo"; color: theme.success; font.pixelSize: theme.fontTiny; font.bold: true }
                                    }
                                }

                                Button {
                                    Layout.fillWidth: true
                                    text: "Personalizar"
                                    enabled: false
                                    ToolTip.text: "A personalização estrutural permanece no editor de Slot de Item já existente."
                                    ToolTip.visible: hovered
                                }
                            }

                            InspectorSection {
                                theme: theme
                                title: "Dados do produto"
                                visible: !!selectedSlot()

                                Label { text: "Nome do Produto"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                TextField {
                                    Layout.fillWidth: true
                                    text: selectedProduct() ? productLabel(selectedProduct()).toUpperCase() : "—"
                                    readOnly: true
                                    font.pixelSize: theme.fontSmall
                                }

                                Label { text: "Imagem"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Rectangle {
                                        Layout.preferredWidth: 48
                                        Layout.preferredHeight: 48
                                        radius: 7
                                        color: theme.surfaceMuted
                                        border.width: 1
                                        border.color: theme.border
                                        clip: true
                                        Image { anchors.fill: parent; anchors.margins: 3; source: selectedSlotImageNode() ? imageSource(selectedSlotImageNode()) : productImageSource(selectedProduct()); fillMode: Image.PreserveAspectFit; asynchronous: true }
                                    }
                                    Label { Layout.fillWidth: true; text: selectedSlotImageNode() ? String(imageSource(selectedSlotImageNode())).split("/").pop() : "Imagem vinculada ao produto"; color: theme.textMuted; font.pixelSize: theme.fontTiny; elide: Text.ElideMiddle }
                                    Button { text: "Trocar"; enabled: !!selectedSlotImageNode(); onClicked: replaceProductImageDialog.open() }
                                }

                                Label { text: "Preço Principal"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    TextField { Layout.preferredWidth: 36; text: "R$"; readOnly: true; horizontalAlignment: Text.AlignHCenter }
                                    TextField { Layout.fillWidth: true; text: priceInteger(selectedProduct(), false); readOnly: true; horizontalAlignment: Text.AlignRight }
                                    TextField { Layout.preferredWidth: 48; text: priceDecimal(selectedProduct(), false); readOnly: true }
                                    TextField { Layout.preferredWidth: 58; text: selectedProduct() ? String(selectedProduct().unit || "UN") : "—"; readOnly: true; horizontalAlignment: Text.AlignHCenter }
                                }

                                Label { text: "Preço Secundário (Promoção)"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    TextField { Layout.preferredWidth: 36; text: "R$"; readOnly: true; horizontalAlignment: Text.AlignHCenter }
                                    TextField { Layout.fillWidth: true; text: priceInteger(selectedProduct(), true); readOnly: true; horizontalAlignment: Text.AlignRight }
                                    TextField { Layout.preferredWidth: 48; text: priceDecimal(selectedProduct(), true); readOnly: true }
                                    Switch { enabled: false; checked: selectedProduct() ? !!(selectedProduct().promotional_price || selectedProduct().promotion) : false }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { Layout.fillWidth: true; text: "Promoção"; color: theme.text; font.pixelSize: theme.fontSmall }
                                    Switch { enabled: false; checked: selectedProduct() ? !!(selectedProduct().promotion || selectedProduct().promotional_price) : false }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { Layout.fillWidth: true; text: "Clube"; color: theme.text; font.pixelSize: theme.fontSmall }
                                    Switch { enabled: false; checked: selectedProduct() ? !!(selectedProduct().club || selectedProduct().club_price) : false }
                                }
                            }

                            InspectorSection {
                                theme: theme
                                title: "Layout e posicionamento"

                                Label { id: inspectorName; Layout.fillWidth: true; text: "Nada selecionado"; color: theme.text; font.pixelSize: theme.fontSmall; font.bold: true; elide: Text.ElideRight }

                                GridLayout {
                                    columns: 4
                                    columnSpacing: 6
                                    rowSpacing: 4
                                    Layout.fillWidth: true
                                    Label { text: "X"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                    Label { text: "Y"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                    Label { text: "Largura"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                    Label { text: "Altura"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                    TextField { id: xField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly; font.pixelSize: theme.fontSmall }
                                    TextField { id: yField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly; font.pixelSize: theme.fontSmall }
                                    TextField { id: wField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly; font.pixelSize: theme.fontSmall }
                                    TextField { id: hField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly; font.pixelSize: theme.fontSmall }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Rotação"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                    TextField { id: rotationField; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly; font.pixelSize: theme.fontSmall }
                                    ToolButton { text: "↺"; enabled: !!anchorNode; onClicked: if (anchorNode) { rotationField.text = "0"; sceneBridge.dispatch('{"name":"rotate","angle":0}') } }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    ToolButton { text: "⇤"; enabled: selectedIds().length >= 2; ToolTip.text: "Alinhar à esquerda"; ToolTip.visible: hovered; onClicked: sceneBridge.dispatch('{"name":"align","mode":"left"}') }
                                    ToolButton { text: "↔"; enabled: selectedIds().length >= 2; ToolTip.text: "Centralizar"; ToolTip.visible: hovered; onClicked: sceneBridge.dispatch('{"name":"align","mode":"center"}') }
                                    ToolButton { text: "⇥"; enabled: selectedIds().length >= 2; ToolTip.text: "Alinhar à direita"; ToolTip.visible: hovered; onClicked: sceneBridge.dispatch('{"name":"align","mode":"right"}') }
                                    Item { Layout.fillWidth: true }
                                    Button {
                                        text: "Redefinir"
                                        enabled: !!anchorNode
                                        onClicked: syncInspector()
                                    }
                                }

                                Button {
                                    text: "Aplicar geometria"
                                    Layout.fillWidth: true
                                    enabled: !!anchorNode && xField.text !== "" && yField.text !== "" && wField.text !== "" && hField.text !== ""
                                    onClicked: {
                                        if (!anchorNode) return
                                        sceneBridge.dispatch(JSON.stringify({"name":"resize","node_id":anchorNode.id,"x":Number(xField.text),"y":Number(yField.text),"width":Number(wField.text),"height":Number(hField.text)}))
                                        sceneBridge.dispatch(JSON.stringify({"name":"rotate","angle":Number(rotationField.text)}))
                                    }
                                }

                                Label { text: "Opacidade"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                Slider { id: opacityField; from: 0; to: 1; stepSize: 0.01; value: 1; Layout.fillWidth: true; onMoved: if (anchorNode) sceneBridge.dispatch(JSON.stringify({"name":"opacity","value":value})) }

                                ColumnLayout {
                                    visible: anchorNode && anchorNode.kind === "text"
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Label { text: "Texto"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                    TextArea { id: textEditor; Layout.fillWidth: true; Layout.preferredHeight: 80; wrapMode: TextEdit.Wrap; font.pixelSize: theme.fontSmall }
                                    Button { text: "Aplicar texto"; Layout.fillWidth: true; onClicked: if (anchorNode) sceneBridge.editText(anchorNode.id, textEditor.text) }
                                }
                            }

                            InspectorSection {
                                theme: theme
                                title: "Ações rápidas"
                                RowLayout {
                                    Layout.fillWidth: true
                                    Button { Layout.fillWidth: true; text: "⧉  Duplicar"; enabled: selectedIds().length > 0; onClicked: sceneBridge.dispatch('{"name":"duplicate"}') }
                                    Button { Layout.fillWidth: true; text: "Excluir"; enabled: selectedIds().length > 0; onClicked: sceneBridge.dispatch('{"name":"delete"}') }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Button { Layout.fillWidth: true; text: "Bloquear"; enabled: selectedIds().length > 0; onClicked: sceneBridge.dispatch('{"name":"lock","value":true}') }
                                    Button { Layout.fillWidth: true; text: "Ocultar"; enabled: selectedIds().length > 0; onClicked: sceneBridge.dispatch('{"name":"hide","value":true}') }
                                }
                            }

                            Item { Layout.preferredHeight: 12 }
                        }
                    }

                    Rectangle {
                        color: theme.surface
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "Camadas"; color: theme.text; font.pixelSize: theme.fontTitle; font.bold: true }
                                Item { Layout.fillWidth: true }
                                Label { text: nodes().length; color: theme.textMuted; font.pixelSize: theme.fontSmall }
                            }
                            ListView {
                                id: layerList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 3
                                reuseItems: true
                                model: nodes().sort(function(a, b) { return b.z_index - a.z_index })
                                ScrollBar.vertical: ScrollBar {}
                                delegate: ItemDelegate {
                                    required property var modelData
                                    width: layerList.width
                                    height: 38
                                    highlighted: isSelected(modelData)
                                    text: (modelData.visible === false ? "◌  " : "◉  ") + (modelData.locked ? "▣  " : "") + (modelData.kind === "group" ? "▦  " : "") + (modelData.name || modelData.kind)
                                    font.pixelSize: theme.fontSmall
                                    onClicked: sceneBridge.selectNodeAdvanced(modelData.id, false, (Qt.application.keyboardModifiers & Qt.ControlModifier) !== 0)
                                }
                            }
                        }
                    }

                    ScrollView {
                        clip: true
                        ColumnLayout {
                            width: Math.max(240, parent.width - 24)
                            x: 12
                            y: 12
                            spacing: 10
                            InspectorSection {
                                theme: theme
                                title: "Dados"
                                Label { text: "Produtos no projeto"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                Label { text: products().length; color: theme.text; font.pixelSize: 22; font.bold: true }
                                Label { text: "Slots na página"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
                                Label { text: slots().length; color: theme.text; font.pixelSize: 22; font.bold: true }
                            }
                            InspectorSection {
                                theme: theme
                                title: "Estado do editor"
                                Label { Layout.fillWidth: true; text: sceneBridge.status; color: theme.textMuted; font.pixelSize: theme.fontSmall; wrapMode: Text.WordWrap }
                                Label { Layout.fillWidth: true; text: "Grid " + (showGrid ? "ativo" : "oculto") + " · Réguas " + (showRulers ? "ativas" : "ocultas") + " · Zoom " + Math.round(zoom * 100) + "%"; color: theme.primary; font.pixelSize: theme.fontSmall; wrapMode: Text.WordWrap }
                            }
                            Item { Layout.preferredHeight: 12 }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: productDragShadow
        visible: productDragGhost.visible
        x: productDragGhost.x + 5
        y: productDragGhost.y + 6
        width: productDragGhost.width
        height: productDragGhost.height
        z: 999998
        radius: theme.radiusLarge
        color: theme.shadowMedium
    }

    Rectangle {
        id: productDragGhost
        visible: productDragActive && !!draggedProduct
        x: productDragX - width / 2
        y: productDragY - height / 2
        width: 268
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
                    source: productImageSource(draggedProduct)
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
                    Label { anchors.centerIn: parent; text: dragHoverSlotId ? "Solte o produto no encarte" : "Arraste o produto para o encarte"; color: "white"; font.bold: true; font.pixelSize: theme.fontTiny }
                }
            }
        }
    }

    FileDialog {
        id: replaceProductImageDialog
        title: "Trocar imagem do produto"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp)", "Todos os arquivos (*)"]
        onAccepted: {
            var node = selectedSlotImageNode()
            if (!node)
                return
            var source = selectedFile.toLocalFile ? selectedFile.toLocalFile() : selectedFile.toString()
            sceneBridge.dispatch(JSON.stringify({"name":"replace_image", "node_id":node.id, "source":source}))
        }
    }
}
