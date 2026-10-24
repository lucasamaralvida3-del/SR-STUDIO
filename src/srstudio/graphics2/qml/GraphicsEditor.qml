import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    width: 1760
    height: 1020
    minimumWidth: 1430
    minimumHeight: 760
    visible: true
    title: "SR Graphics Engine 2.0"

    property var scene: JSON.parse(sceneBridge.sceneJson)
    property var page: activePage()
    property real zoom: 0.72
    // Beta 42: studio navigation mirrors the supplied SR Studio 5.0 reference.
    property int studioSection: 0
    property int studioNavigation: 2
    property int autoLayoutVariation: 0
    property string productQuery: ""
    property string productFilter: "Todos os produtos"
    property int visibleProductLimit: 12
    property bool showProductionGate: false
    property bool showAdvancedSlotActions: false

    function filteredProducts() {
        var query = productQuery.toLocaleLowerCase().trim()
        return products().filter(function(p) {
            var searchable = (productLabel(p) + " " + String(p.id || p.product_id || "")).toLocaleLowerCase()
            var hasImage = !!(p.image_path || p.image)
            return (!query || searchable.indexOf(query) !== -1)
                && (productFilter === "Todos os produtos"
                    || (productFilter === "Com imagem" && hasImage)
                    || (productFilter === "Sem imagem" && !hasImage))
        }).slice(0, visibleProductLimit)
    }

    function createBlueSlot() {
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
            "name": "add_item_slot", "preset_id": "limpeza-blue-v1"
        })))
        if (result.ok && result.payload) {
            selectedSlotId = String(result.payload.slot_id || "")
            smartSlotEditMode = true
            smartSlotInspectionMode = true
        }
    }

    function createIndividualSlot() {
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
            "name": "add_item_slot", "preset_id": "individual-beta44"
        })))
        if (result.ok && result.payload) {
            selectedSlotId = String(result.payload.slot_id || "")
            smartSlotEditMode = true
            smartSlotInspectionMode = true
        }
    }

    function createMultiSlot(count) {
        var modes = ["auto", "one", "two"]
        var mode = modes[slotPriceMode.currentIndex] || "auto"
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
            "name": "add_multi_item_slot", "count": count, "price_mode": mode
        })))
        if (result.ok && result.payload) {
            var created = result.payload.slot_ids || []
            selectedSlotId = created.length ? String(created[0]) : ""
            smartSlotEditMode = true
            smartSlotInspectionMode = true
        }
    }

    function promotionPreviewSlots(mode) {
        if (mode === "individual")
            return [{x:.20,y:.31,w:.60,h:.63}]
        if (mode === "six" || mode === "seven") {
            var out = [{x:.04,y:.29,w:.43,h:.40},
                       {x:.49,y:.29,w:.46,h:.19},
                       {x:.49,y:.50,w:.46,h:.19}]
            var n = mode === "six" ? 3 : 4
            for (var i = 0; i < n; i++)
                out.push({x:.04 + i*(.91/n),y:.72,w:.91/n-.008,h:.24})
            return out
        }
        var cards = []
        for (var row = 0; row < 3; row++) {
            var columns = row === 2 ? 5 : 3
            for (var col = 0; col < columns; col++)
                cards.push({x:.04+col*(.92/columns),y:.29+row*.225,
                           w:.92/columns-.008,h:.215})
        }
        return cards
    }

    function selectedPicture() {
        var selected = selectedNode()
        return selected && selected.kind === "image" ? selected : null
    }

    function removeCurrentBackground() {
        if (selectedSlotId !== "")
            sceneBridge.removeSlotBackground(selectedSlotId)
        else if (selectedPicture())
            sceneBridge.removeBackground(selectedPicture().id)
    }

    FileDialog {
        id: replaceSelectedImageDialog
        title: "Substituir imagem selecionada"
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)"]
        onAccepted: {
            if (anchorNode && anchorNode.kind === "image")
                sceneBridge.dispatch(JSON.stringify({"name":"replace_image","node_id":anchorNode.id,"source":selectedFile.toString()}))
        }
    }
    FileDialog {
        id: sourceImportDialog
        title: "Importar planilha ou apresentação"
        nameFilters: ["Planilhas e apresentações (*.xlsx *.xls *.csv *.pptx)"]
        onAccepted: sceneBridge.importSource(selectedFile.toString())
    }
    function moveActivePage(step) {
        var pages = scene.pages || []
        var pos = pages.findIndex(function(p) { return p.id === scene.active_page_id })
        var target = pos + step
        if (pos >= 0 && target >= 0 && target < pages.length)
            sceneBridge.dispatch(JSON.stringify({"name":"reorder_page","page_id":pages[pos].id,"target_index":target}))
    }
    FileDialog {
        id: saveProjectDialog
        title: "Salvar projeto SR Studio"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Cena SR Studio (*.srscene)"]
        onAccepted: sceneBridge.saveSceneAs(selectedFile.toString())
    }
    FileDialog {
        id: exportPdfDialog
        title: "Exportar encarte em PDF"
        fileMode: FileDialog.SaveFile
        nameFilters: ["PDF (*.pdf)"]
        onAccepted: sceneBridge.exportPdf(selectedFile.toString())
    }
    FileDialog {
        id: exportPngDialog
        title: "Exportar encarte em PNG"
        fileMode: FileDialog.SaveFile
        nameFilters: ["PNG (*.png)"]
        onAccepted: sceneBridge.exportPng(selectedFile.toString())
    }
    property bool showGrid: true
    property bool showRulers: true
    property real gridStep: 50
    property string selectedSlotId: ""
    property string pendingImageProductId: ""
    property string pendingImageProductName: ""
    FileDialog {
        id: productImageDialog
        title: "Adicionar imagem ao produto"
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)"]
        onAccepted: sceneBridge.attachProductImage(window.pendingImageProductId, window.pendingImageProductName, selectedFile.toString())
    }
    property string hoveredSlotId: ""
    property bool smartSlotInspectionMode: false
    property bool smartSlotEditMode: false
    property bool smartSlotSnap: true
    property bool autoRemoveProductBackground: true
    property real smartSlotLastCommitMs: 0
    property int smartSlotPreviewEvents: 0
    property int smartSlotPreviewUpdates: 0
    property string smartSlotInteractionKind: ""
    // One temporary GPU-side transform for the active slot: no Python command,
    // undo snapshot, full-scene JSON or image rebinding on mouse move.
    property var activeSlotPreview: null
    property var activeSlotPreviewMembers: ({})
    property var activeSlotBaseBounds: null

    function previewMemberIds(slot) {
        var ids = ({})
        if (!slot || !page)
            return ids
        var roots = []
        var rootId = slot.metadata ? String(slot.metadata.root_node_id || "") : ""
        if (rootId && page.nodes[rootId])
            roots.push(rootId)
        var roleMap = slot.node_by_role || {}
        for (var role in roleMap) {
            var nodeId = String(roleMap[role] || "")
            if (nodeId && page.nodes[nodeId])
                roots.push(nodeId)
        }
        var meta = slot.metadata || ({})
        var others = [].concat(meta.decorative_nodes || [], meta.limpeza_blue_nodes || [], meta.source_node_ids || [])
        var areas = meta.role_area_nodes || ({})
        for (var area in areas)
            others.push(String(areas[area]))
        for (var oi = 0; oi < others.length; ++oi)
            roots.push(String(others[oi]))
        var extras = meta.extra_bindings || ({})
        for (var key in extras)
            for (var ei = 0; ei < extras[key].length; ++ei)
                roots.push(String(extras[key][ei]))
        // Traverse children only once on press, never for each mouse event.
        var pending = roots.slice()
        while (pending.length) {
            var id = pending.pop()
            if (ids[id] || !page.nodes[id])
                continue
            ids[id] = true
            var children = page.nodes[id].children || []
            for (var ci = 0; ci < children.length; ++ci)
                pending.push(String(children[ci]))
        }
        // For highly detailed imported cards, transforming every vector path
        // and rerasterizing it on each pointer event is prohibitively slow.
        // Use an outline-only transient preview; artwork moves on mouse release.
        if ((slot.metadata && slot.metadata.limpeza_blue_profile) || Object.keys(ids).length > 24)
            return ({})
        return ids
    }

    function liveSlotNodeRect(node) {
        // Fast bailout BEFORE reading activeSlotPreview: ordinary artwork must
        // not acquire a dependency on each mouse movement, or the entire scene
        // rerenders continuously (especially imported PPTX with many nodes).
        if (!activeSlotPreviewMembers[node.id])
            return node.transform
        var preview = activeSlotPreview
        var base = activeSlotBaseBounds
        if (!preview || !base)
            return node.transform
        var t = node.transform
        var sx = preview.width / Math.max(1, base.width)
        var sy = preview.height / Math.max(1, base.height)
        return {
            "x": preview.x + (Number(t.x) - base.x) * sx,
            "y": preview.y + (Number(t.y) - base.y) * sy,
            "width": Math.max(1, Number(t.width) * sx),
            "height": Math.max(1, Number(t.height) * sy)
        }
    }


    function clearSlotPreview() {
        activeSlotPreview = null
        activeSlotBaseBounds = null
        activeSlotPreviewMembers = ({})
    }
    property var anchorNode: selectedNode()
    property var draggedProduct: null
    property bool productDragActive: false
    property real productDragX: 0
    property real productDragY: 0
    property string dragHoverSlotId: ""

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
        // Beta 44: the Blue slot is unchanged; include only the two
        // explicit new manual presets, never revive retired legacy presets.
        return page ? Object.values(page.slots || {}).filter(function(slot) {
            var meta = slot.metadata || {}
            return meta.limpeza_blue_profile === "limpeza-blue-v1"
                || meta.preset_id === "individual-beta44"
                || meta.preset_id === "multi-cell-beta44"
        }) : []
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
        // The previous bounding box came from old role metadata and could be
        // hundreds of pixels away from the visible card after move/resize.
        // Always anchor manual Azul slots to the ACTUAL scene root.
        var rootId = slot.metadata ? String(slot.metadata.root_node_id || "") : ""
        var root = rootId && page.nodes ? page.nodes[rootId] : null
        if (root && root.transform) {
            var t = root.transform
            return {"x": Number(t.x), "y": Number(t.y),
                    "width": Number(t.width), "height": Number(t.height)}
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
                    if (result.ok && result.payload && result.payload.drop_target) {
                        selectedSlotId = String(result.payload.drop_target.slot_id || selectedSlotId)
                        if (autoRemoveProductBackground && selectedSlotId)
                            sceneBridge.removeSlotBackground(selectedSlotId)
                    }
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
        var chosenSlot = selectedSlotId
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({"name": "bind_product", "slot_id": chosenSlot, "product_id": product.id})))
        if (result.ok && autoRemoveProductBackground)
            sceneBridge.removeSlotBackground(chosenSlot)
    }

    function syncInspector() {
        var node = selectedNode()
        anchorNode = node
        if (!node) {
            inspectorName.text = "Nada selecionado"
            textEditor.text = ""
            return
        }
        inspectorName.text = node.name || node.kind || "Elemento"
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



    // Shortcuts once owned by ProjectActions.qml. Preserve them after
    // eliminating the floating legacy project toolbar.
    Shortcut { sequence: StandardKey.Save; onActivated: saveProjectDialog.open() }
    Shortcut { sequence: StandardKey.Copy; onActivated: sceneBridge.dispatch('{"name":"copy"}') }
    Shortcut { sequence: StandardKey.Paste; onActivated: sceneBridge.dispatch('{"name":"paste"}') }
    header: null

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            Rectangle {
                SplitView.preferredWidth: 332
                SplitView.minimumWidth: 285
                color: "#FFFFFF"
                border.color: "#E5EAF4"
                RowLayout {
                    anchors.fill: parent
                    spacing: 0
                    Rectangle {
                        Layout.preferredWidth: 67
                        Layout.fillHeight: true
                        color: "#FBFCFF"
                        border.color: "#EEF1F8"
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.topMargin: 11
                            spacing: 7
                            Repeater {
                                model: [
                                    { icon:"⬡", title:"Produtos" }, { icon:"⬡", title:"Slots" },
                                    { icon:"♧", title:"Layouts" }, { icon:"▧", title:"Imagens" },
                                    { icon:"T", title:"Texto" }, { icon:"♧", title:"Formas" },
                                    { icon:"▨", title:"Fundos" }, { icon:"▱", title:"Camadas" },
                                    { icon:"☷", title:"Projeto" }
                                ]
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 73
                                    Layout.leftMargin: 5
                                    Layout.rightMargin: 5
                                    radius: 9
                                    color: studioSection === index ? "#EFF3FF" : "transparent"
                                    ColumnLayout {
                                        anchors.centerIn: parent
                                        spacing: 5
                                        Label { text: modelData.icon; Layout.alignment: Qt.AlignHCenter; color: studioSection === index ? "#2C4BFA" : "#4C577F"; font.pixelSize: 24 }
                                        Label { text: modelData.title; Layout.alignment: Qt.AlignHCenter; color: studioSection === index ? "#284DFF" : "#425072"; font.pixelSize: 9; font.bold: studioSection === index }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: studioSection = index }
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                    ColumnLayout {
                        Layout.fillHeight: true
                        Layout.fillWidth: true
                        Layout.margins: 13
                        spacing: 11
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: ["Produtos","Slots","Layouts de Promoção","Imagens","Texto","Formas","Fundos","Camadas","Projeto"][studioSection]
                                color: "#111B38"; font.pixelSize: 15; font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            ToolButton { text: "⌄"; onClicked: studioSection = 0 }
                        }
                        ColumnLayout {
                            Layout.fillHeight: true
                            Layout.fillWidth: true
                            visible: studioSection === 0 || studioSection === 3
                            spacing: 11
                            RowLayout {
                                Layout.fillWidth: true
                                TextField { Layout.fillWidth: true; placeholderText: "⌕  Buscar produtos..."; text: productQuery; onTextChanged: productQuery = text; font.pixelSize: 11 }
                                ToolButton { text: "▽"; onClicked: productFilter = productFilter === "Sem imagem" ? "Todos os produtos" : "Sem imagem" }
                            }
                            ComboBox {
                                Layout.fillWidth: true
                                model: ["Todos os produtos","Com imagem","Sem imagem"]
                                onActivated: productFilter = currentText
                            }
                            Label { text: "Destino do produto"; font.pixelSize: 10; color: "#79849A" }
                            ComboBox {
                                id: slotCombo
                                Layout.fillWidth: true
                                model: slots()
                                textRole: "name"
                                valueRole: "id"
                                onActivated: selectedSlotId = currentValue
                            }
                                                        ListView {
                                id: productList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 8
                                model: filteredProducts()
                                ScrollBar.vertical: ScrollBar {}
                                delegate: Rectangle {
                                    id: productCard
                                    required property var modelData
                                    width: productList.width - 4
                                    height: 99
                                    radius: 9
                                    color: productMouse.containsMouse ? "#F1F6FF" : "#FFFFFF"
                                    border.color: productMouse.dragging ? "#0F5BD8" : "#D9E4F2"
                                    border.width: productMouse.dragging ? 2 : 1
                                    property var productData: modelData

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 9
                                        spacing: 9
                                        Rectangle {
                                            Layout.preferredWidth: 64
                                            Layout.preferredHeight: 66
                                            radius: 5
                                            color: "#FAFBFE"
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
                                            Label { Layout.fillWidth: true; text: modelData.display_name || modelData.name || modelData.original_name || "Produto"; color: "#111827"; font.bold: true; font.pixelSize: 12; elide: Text.ElideRight }
                                            Label { text: (modelData.unit || "UN") + (modelData.category ? " · " + modelData.category : ""); color: "#64748B"; font.pixelSize: 10 }
                                            Label { text: modelData.price ? ("R$ " + String(modelData.price).replace(".", ",")) : "Sem preço"; color: "#0F5BD8"; font.bold: true; font.pixelSize: 14 }
                                        }
                                        ToolButton { text: "+"; font.pixelSize: 18; enabled: selectedSlotId !== ""; onClicked: bindProduct(modelData) }
                                    }
                                    MouseArea {
                                        id: productMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                                        preventStealing: dragging
                                        property real pressX: 0
                                        property real pressY: 0
                                        property bool dragging: false
                                        onPressed: {
                                            if (mouse.button === Qt.RightButton) {
                                                productActions.popup()
                                                return
                                            }
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
                                                beginProductDrag(productMouse, mouse.x, mouse.y, productCard.productData)
                                            }
                                            if (dragging)
                                                updateProductDrag(productMouse, mouse.x, mouse.y, productCard.productData)
                                        }
                                        onReleased: {
                                            if (dragging)
                                                finishProductDrag(productMouse, mouse.x, mouse.y, productCard.productData)
                                            else
                                                cancelProductDrag()
                                            dragging = false
                                        }
                                        onCanceled: {
                                            dragging = false
                                            cancelProductDrag()
                                        }
                                        onDoubleClicked: if (selectedSlotId) bindProduct(productCard.productData)
                                    Menu {
                                        id: productActions
                                        MenuItem {
                                            text: "Adicionar imagem"
                                            onTriggered: {
                                                var p = productCard.productData
                                                window.pendingImageProductId = String(p.id || p.product_id || "")
                                                window.pendingImageProductName = productLabel(p)
                                                productImageDialog.open()
                                            }
                                        }
                                    }
                                    }
                                }
                                Label { anchors.centerIn: parent; visible: productList.count === 0; text: "Importe uma planilha para carregar produtos."; width: productList.width - 30; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; color: "#94A3B8" }
                            }

                            Button {
                                Layout.fillWidth: true
                                text: "Ver mais produtos"
                                flat: true
                                onClicked: visibleProductLimit += 24
                            }
                        }
                        ColumnLayout {
                            Layout.fillHeight: true
                            Layout.fillWidth: true
                            visible: studioSection === 7
                            spacing: 7
                                                    ColumnLayout {
                            spacing: 6
                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "Camadas"; font.bold: true; color: "#334155" }
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
                                    text: (modelData.visible === false ? "◌  " : "◉  ") + (modelData.locked ? "🔒  " : "") + (modelData.kind === "group" ? "▣  " : "") + (modelData.name || modelData.kind)
                                    onClicked: sceneBridge.selectNodeAdvanced(modelData.id, false, (Qt.application.keyboardModifiers & Qt.ControlModifier) !== 0)
                                }
                            }
                        }

                        }
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            visible: studioSection === 2
                            clip: true
                            ColumnLayout {
                                width: 235
                                spacing: 9
                                Label { text: "Layouts promocionais"; color: "#284F8F"; font.bold: true }
                                Label { text: "Área superior reservada para logo"; color: "#64748B"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Repeater {
                                    model: [
                                        {"label":"Destaque individual", "mode":"individual"},
                                        {"label":"11 produtos", "mode":"eleven"},
                                        {"label":"7 produtos", "mode":"seven"},
                                        {"label":"6 produtos", "mode":"six"}
                                    ]
                                    delegate: Rectangle {
                                        id: previewLayoutCard
                                        required property var modelData
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 153
                                        color: "#FFFFFF"
                                        border.color: "#CFD9EA"
                                        radius: 9
                                        Label {
                                            x: 8; y: 5
                                            font.bold: true
                                            color: "#284F8F"
                                            text: previewLayoutCard.modelData.label
                                        }
                                        Rectangle {
                                            id: previewPoster
                                            x: 38; y: 29; width: parent.width - 76; height: 119
                                            color: "#F8FAFC"
                                            border.color: "#DFE7F2"
                                            Rectangle {
                                                x: 0; y: 0; width: parent.width; height: parent.height*.26
                                                color: "#EAF0F9"
                                                Label { anchors.centerIn: parent; text: "ÁREA DA LOGO"; font.pixelSize: 8; color: "#64748B" }
                                            }
                                            Repeater {
                                                model: window.promotionPreviewSlots(previewLayoutCard.modelData.mode)
                                                delegate: Rectangle {
                                                    required property var modelData
                                                    x: modelData.x * previewPoster.width
                                                    y: modelData.y * previewPoster.height
                                                    width: modelData.w * previewPoster.width
                                                    height: modelData.h * previewPoster.height
                                                    color: "#FFFFFF"; border.color: "#CAD7E8"
                                                    Rectangle {
                                                        anchors.left: parent.left; anchors.right: parent.right
                                                        anchors.bottom: parent.bottom
                                                        height: parent.height*.28
                                                        color: "#295599"
                                                    }
                                                }
                                            }
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: sceneBridge.dispatch(JSON.stringify({
                                                "name":"apply_promotion_layout",
                                                "mode":previewLayoutCard.modelData.mode
                                            }))
                                        }
                                    }
                                }
                                Label { text: "Auto Layout"; color: "#284F8F"; font.bold: true }
                                SpinBox { id: autoLayoutCount; from: 1; to: 24; value: 6; editable: true; Layout.fillWidth: true }
                                Button {
                                    Layout.fillWidth: true
                                    text: "Criar Auto Layout"
                                    onClicked: sceneBridge.dispatch(JSON.stringify({
                                        "name":"apply_promotion_layout",
                                        "mode":"auto",
                                        "count":autoLayoutCount.value,
                                        "variation":window.autoLayoutVariation++
                                    }))
                                }
                            }
                        }
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            visible: studioSection === 8
                            clip: true
                            ColumnLayout {
                                width: 235
                                spacing: 7
                                Label { text: "Ações do projeto"; font.bold: true; color: "#263D71" }
                                Button { text: "+ Slot Azul"; Layout.fillWidth: true; onClicked: createBlueSlot() }
                                Button { text: "Ajustar Smart Slots"; Layout.fillWidth: true; checkable: true; checked: smartSlotEditMode; onClicked: { smartSlotEditMode = checked; smartSlotInspectionMode = checked } }
                                Button { text: "Copiar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"copy"}') }
                                Button { text: "Colar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"paste"}') }
                                Button { text: "Salvar"; Layout.fillWidth: true; onClicked: saveProjectDialog.open() }
                                Button { text: "Recuperar"; Layout.fillWidth: true; onClicked: sceneBridge.recoverLatest() }
                                Button { text: "Importar PPTX / Planilha"; Layout.fillWidth: true; onClicked: sourceImportDialog.open() }
                                Button { text: "PDF"; Layout.fillWidth: true; onClicked: exportPdfDialog.open() }
                                Button { text: "PNG"; Layout.fillWidth: true; onClicked: exportPngDialog.open() }
                                Button { text: "Duplicar página"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"duplicate_page"}') }
                                Button { text: "Mover página para esquerda"; Layout.fillWidth: true; onClicked: window.moveActivePage(-1) }
                                Button { text: "Mover página para direita"; Layout.fillWidth: true; onClicked: window.moveActivePage(1) }
                            }
                        }
                        ScrollView {
                            Layout.fillHeight: true
                            Layout.fillWidth: true
                            visible: studioSection === 1
                            clip: true
                            ColumnLayout {
                                width: 235
                                spacing: 11
                                // Visual thumbnails stay scrollable on laptop screens.

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 175
                                visible: studioSection === 1
                                color: "#FFFFFF"
                                border.color: "#CFD9EA"
                                radius: 10
                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 7
                                    Label { text: "Slot Azul"; font.bold: true; color: "#284F8F" }
                                    Rectangle {
                                        width: parent.width
                                        height: 102
                                        color: "#F8FAFC"
                                        radius: 6
                                        Rectangle {
                                            x: 8; y: 13; width: parent.width * 0.43; height: 60
                                            radius: 10; color: "#E5EDF8"; border.color: "#295599"; border.width: 3
                                            Label { anchors.centerIn: parent; text: "PRODUTO"; color: "#295599"; font.pixelSize: 10; font.bold: true }
                                        }
                                        Rectangle {
                                            anchors.right: parent.right; anchors.bottom: parent.bottom
                                            anchors.rightMargin: 7; anchors.bottomMargin: 7
                                            width: parent.width * 0.53; height: 55
                                            color: "#295599"; radius: 9
                                            Label { anchors.centerIn: parent; text: "R$  9,99"; color: "white"; font.pixelSize: 19; font.bold: true }
                                        }
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: createBlueSlot()
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 138
                                visible: studioSection === 1
                                color: "#FFFFFF"; border.color: "#CFD9EA"; radius: 10
                                Column {
                                    anchors.fill: parent; anchors.margins: 10; spacing: 7
                                    Label { text: "Individual"; color: "#284F8F"; font.bold: true }
                                    Rectangle {
                                        width: parent.width; height: 91; color: "#F7FAFE"
                                        radius: 6
                                        Rectangle { x: 8; y: 7; width: parent.width * .49; height: 76; radius: 7; color: "#E7EEF9"
                                            Label { anchors.centerIn: parent; text: "PRODUTO"; color: "#456AA2"; font.pixelSize: 10 }
                                        }
                                        Rectangle { anchors.right: parent.right; anchors.rightMargin: 8; anchors.bottom: parent.bottom
                                            anchors.bottomMargin: 7; width: parent.width * .43; height: 43; radius: 7; color: "#295599"
                                            Label { anchors.centerIn: parent; text: "R$ 9,99"; color: "white"; font.bold: true; font.pixelSize: 17 }
                                        }
                                    }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: createIndividualSlot() }
                            }
                            Label {
                                visible: studioSection === 1
                                text: "Preços dos novos slots"
                                color: "#284F8F"; font.bold: true
                            }
                            ComboBox {
                                id: slotPriceMode
                                visible: studioSection === 1
                                Layout.fillWidth: true
                                model: ["Automático", "1 preço", "2 preços"]
                                currentIndex: 0
                            }
                            Repeater {
                                model: [5, 6]
                                delegate: Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 130
                                    visible: studioSection === 1
                                    color: "#FFFFFF"
                                    border.color: "#CFD9EA"
                                    radius: 10
                                    Label {
                                        x: 10; y: 7
                                        text: "Multi Itens — " + modelData + " produtos"
                                        color: "#284F8F"; font.bold: true
                                    }
                                    Row {
                                        x: 8; y: 34
                                        width: parent.width - 16; height: 86
                                        spacing: 2
                                        Repeater {
                                            model: parent.parent.modelData
                                            delegate: Rectangle {
                                                width: (parent.width - (parent.parent.modelData - 1) * 2) / parent.parent.modelData
                                                height: parent.height
                                                color: "#F7FAFE"
                                                border.color: "#D7E1F0"
                                                Rectangle {
                                                    x: 3; y: 19
                                                    width: parent.width - 6; height: 35
                                                    radius: 4; color: "#E0E8F6"
                                                }
                                                Rectangle {
                                                    anchors.left: parent.left; anchors.right: parent.right
                                                    anchors.bottom: parent.bottom; height: 27
                                                    color: "#295599"
                                                    Label {
                                                        anchors.centerIn: parent
                                                        text: "9,99"
                                                        color: "white"; font.bold: true
                                                        font.pixelSize: 9
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: createMultiSlot(Number(parent.modelData))
                                    }
                                }
                            }
                            Button {
                                visible: studioSection === 1
                                Layout.fillWidth: true
                                text: "Aplicar modo de preço ao slot selecionado"
                                enabled: selectedSlotId !== ""
                                onClicked: {
                                    var modes = ["auto", "one", "two"]
                                    sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_item_price_mode",
                                        "slot_id":selectedSlotId,
                                        "mode":modes[slotPriceMode.currentIndex]
                                    }))
                                }
                            }
                            }
                        }
                        ColumnLayout {
                            Layout.fillHeight: true
                            Layout.fillWidth: true
                            visible: studioSection === 4 || studioSection === 5 || studioSection === 6
                            spacing: 11
                            Button { Layout.fillWidth: true; visible: studioSection === 4; text: "+ Texto"; onClicked: sceneBridge.dispatch('{"name":"add_text"}') }
                            Button { Layout.fillWidth: true; visible: studioSection === 5; text: "+ Forma"; onClicked: sceneBridge.dispatch('{"name":"add_rect"}') }
                            CheckBox { visible: studioSection === 6; text: "Mostrar grade"; checked: showGrid; onToggled: showGrid = checked }
                            CheckBox { visible: studioSection === 6; text: "Mostrar réguas"; checked: showRulers; onToggled: showRulers = checked }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }

            Rectangle {
                id: workspace
                SplitView.fillWidth: true
                SplitView.fillHeight: true
                color: "#F4F7FD"

                Rectangle {
                    height: 49
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    color: "white"
                    radius: 8
                    border.color: "#E8EBF4"
                    z: 20000
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 3
                        ToolButton { text: "↖"; highlighted: !smartSlotEditMode; ToolTip.text: "Seleção"; ToolTip.visible: hovered; onClicked: smartSlotEditMode = false }
                        ToolButton { text: "▧"; highlighted: smartSlotEditMode; ToolTip.text: "Ajustar Smart Slot"; ToolTip.visible: hovered; onClicked: { smartSlotEditMode = !smartSlotEditMode; smartSlotInspectionMode = smartSlotEditMode } }

                        ToolButton {
                            text: "⋯"
                            ToolTip.text: "Opções do Smart Slot"; ToolTip.visible: hovered
                            onClicked: studioSlotMenu.popup()
                            Menu {
                                id: studioSlotMenu
                                MenuItem { text: "Remover Fundo"; onTriggered: removeCurrentBackground() }
                                MenuItem { text: "Restaurar Auto"; enabled: selectedSlotId !== ""; onTriggered: sceneBridge.dispatch(JSON.stringify({"name":"restore_smart_slot_auto","slot_id":selectedSlotId})) }
                                MenuItem { text: "Excluir Slot"; enabled: selectedSlotId !== ""; onTriggered: sceneBridge.dispatch(JSON.stringify({"name":"delete_smart_slot","slot_id":selectedSlotId})) }
                                MenuItem { text: "Não-produto"; enabled: selectedSlotId !== ""; onTriggered: sceneBridge.dispatch(JSON.stringify({"name":"mark_smart_slot_non_product","slot_id":selectedSlotId})) }
                                MenuItem { text: "Fundo automático"; checkable: true; checked: autoRemoveProductBackground; onTriggered: autoRemoveProductBackground = checked }
                            }
                        }
                        ToolButton { text: "T"; ToolTip.text: "Texto"; ToolTip.visible: hovered; onClicked: sceneBridge.dispatch('{"name":"add_text"}') }
                        ToolButton { text: "▧"; ToolTip.text: "Imagens"; ToolTip.visible: hovered; onClicked: studioSection = 3 }
                        ToolSeparator {}
                        ToolButton { text: "↶"; enabled: !!scene.editor && scene.editor.can_undo; onClicked: sceneBridge.undo() }
                        ToolButton { text: "↷"; enabled: !!scene.editor && scene.editor.can_redo; onClicked: sceneBridge.redo() }
                        Item { Layout.fillWidth: true }
                        ToolButton { text: "−"; onClicked: zoom = Math.max(0.12, zoom - 0.1) }
                        Label { text: Math.round(zoom * 100) + "%"; color: "#1C2B4D"; font.bold: true; font.pixelSize: 12 }
                        ToolButton { text: "+"; onClicked: zoom = Math.min(3.5, zoom + 0.1) }
                        ToolButton { text: "✥"; onClicked: showRulers = !showRulers }
                    }
                }

                Flickable {
                    id: viewport
                    anchors.fill: parent
                    anchors.topMargin: 52
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
                            border.color: productDragActive && dragHoverSlotId ? "#16A34A" : "#BFCBDA"
                            border.width: productDragActive && dragHoverSlotId ? 2 : 1
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
                                    // During drag move/re-size the *actual slot artwork*,
                                    // including its imported product image, at GPU speed.
                                    readonly property var fastBounds: window.liveSlotNodeRect(modelData)
                                    x: Number(fastBounds.x) * zoom
                                    y: Number(fastBounds.y) * zoom
                                    width: Math.max(1, Number(fastBounds.width) * zoom)
                                    height: Math.max(1, Number(fastBounds.height) * zoom)
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
                                        drag.target: parent
                                        // The selection rectangle owns pointer gestures
                                        // only in slot edit mode. In normal mode images
                                        // and text remain independently selectable.
                                        enabled: !smartSlotEditMode && !effectiveLocked(modelData)
                                        preventStealing: true
                                        // Selecting on press emitted sceneChanged and rebuilt the
                                        // delegate while Qt still held the drag. This detached
                                        // drag.target and made moving images feel frozen.
                                        onReleased: {
                                            var dx = (parent.x / zoom) - Number(modelData.transform.x)
                                            var dy = (parent.y / zoom) - Number(modelData.transform.y)
                                            var id = String(modelData.id)
                                            var shift = (mouse.modifiers & Qt.ShiftModifier) !== 0
                                            var ctrl = (mouse.modifiers & Qt.ControlModifier) !== 0
                                            sceneBridge.selectNodeAdvanced(id, shift, ctrl)
                                            if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001)
                                                sceneBridge.moveSelectionAtZoom(dx, dy, zoom)
                                        }
                                        onDoubleClicked: {
                                            sceneBridge.selectNodeAdvanced(modelData.id, false, false)
                                            if (modelData.kind === "text")
                                                textEditor.forceActiveFocus()
                                        }
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
                                    property bool isDropTarget: productDragActive && dragHoverSlotId === modelData.id
                                    property bool isSelectedSlot: selectedSlotId === modelData.id
                                    property bool isHoveredSlot: hoveredSlotId === modelData.id
                                    property bool showSlotOverlay: smartSlotEditMode || smartSlotInspectionMode || productDragActive || isSelectedSlot || isHoveredSlot
                                    x: displayBounds.x * zoom
                                    y: displayBounds.y * zoom
                                    width: displayBounds.width * zoom
                                    height: displayBounds.height * zoom
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
                                        // Start at the original bounds, avoid an immediate
                                        // snap/jump as soon as the user presses the mouse.
                                        var value = clampPreview(raw)
                                        window.activeSlotBaseBounds = value
                                        window.activeSlotPreviewMembers = window.previewMemberIds(slotOverlay.modelData)
                                        window.activeSlotPreview = value
                                        previewActive = true
                                        pendingPreviewBounds = value
                                        preview_bounds = value
                                        lastPreviewAppliedMs = Date.now()
                                        previewEventCount = 0
                                        previewUpdateCount = 0
                                        window.smartSlotInteractionKind = String(kind || "")
                                    }

                                    function queuePreview(raw, force) {
                                        if (!previewActive)
                                            return
                                        // Keep 1:1 mouse movement fluid. Snap only once at release.
                                        pendingPreviewBounds = force ? snapPreview(raw) : clampPreview(raw)
                                        previewEventCount += 1
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
                                        // Only the affected nodes have reactive fastBounds.
                                        window.activeSlotPreview = pendingPreviewBounds
                                        lastPreviewAppliedMs = Date.now()
                                        previewUpdateCount += 1
                                        window.smartSlotPreviewUpdates += 1
                                    }

                                    function commitPreview(raw, kind) {
                                        if (!previewActive)
                                            return
                                        queuePreview(raw, true)
                                        var finalBounds = preview_bounds
                                        var started = Date.now()
                                        // The source-of-truth commit remains ONE operation
                                        // at release; drop the transient transform first.
                                        window.clearSlotPreview()
                                        sceneBridge.dispatch(JSON.stringify({
                                            "name":"adjust_smart_slot",
                                            "slot_id":slotOverlay.modelData.id,
                                            "x":finalBounds.x,
                                            "y":finalBounds.y,
                                            "width":finalBounds.width,
                                            "height":finalBounds.height,
                                            "snap":smartSlotSnap
                                        }))
                                        window.smartSlotLastCommitMs = Math.max(0, Date.now() - started)
                                        window.smartSlotInteractionKind = String(kind || "")
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
                                        anchors.fill: parent
                                        color: isDropTarget ? "#16A34A2A" : (isSelectedSlot ? "#0F5BD811" : (productDragActive ? "#0F5BD808" : "transparent"))
                                        border.width: isDropTarget ? 3 : (isSelectedSlot ? 2 : 1)
                                        border.color: isDropTarget ? "#16A34A" : (isSelectedSlot ? "#0F5BD8" : "#0F5BD855")
                                        radius: 4
                                    }
                                    Label {
                                        anchors.centerIn: parent
                                        visible: slotOverlay.previewActive && Object.keys(window.activeSlotPreviewMembers).length === 0
                                        text: "PRÉVIA LEVE · SOLTE PARA APLICAR"
                                        color: "#0F5BD8"
                                        font.bold: true
                                        font.pixelSize: 12
                                        padding: 7
                                        background: Rectangle { color: "#FFFFFFD9"; radius: 5 }
                                        z: 12
                                    }
                                    Label {
                                        x: 4; y: 4
                                        text: isDropTarget ? "SOLTAR PRODUTO AQUI" : ((modelData.metadata && modelData.metadata.display_label) ? modelData.metadata.display_label : (modelData.name || "Smart Slot"))
                                        color: "white"
                                        font.bold: true
                                        font.pixelSize: 9
                                        padding: 3
                                        background: Rectangle { color: isDropTarget ? "#16A34A" : (isSelectedSlot ? "#0F5BD8" : "#64748BAA"); radius: 3 }
                                    }
                                    MouseArea {
                                        id: slotMoveArea
                                        objectName: "smartSlotMoveArea-" + String(slotOverlay.modelData.id || "")
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        enabled: smartSlotEditMode || productDragActive
                                        hoverEnabled: smartSlotEditMode || productDragActive
                                        preventStealing: smartSlotEditMode
                                        property real startGlobalX: 0
                                        property real startGlobalY: 0
                                        property var startBounds: ({"x":0,"y":0,"width":1,"height":1})
                                        onEntered: hoveredSlotId = slotOverlay.modelData.id
                                        onExited: if (hoveredSlotId === slotOverlay.modelData.id) hoveredSlotId = ""
                                        onPressed: {
                                            selectedSlotId = slotOverlay.modelData.id
                                            if (!smartSlotEditMode)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            startGlobalX = point.x / zoom
                                            startGlobalY = point.y / zoom
                                            startBounds = {"x":slotOverlay.bounds.x,"y":slotOverlay.bounds.y,"width":slotOverlay.bounds.width,"height":slotOverlay.bounds.height}
                                            slotOverlay.beginPreview(startBounds, "move")
                                        }
                                        onClicked: selectedSlotId = slotOverlay.modelData.id
                                        onPositionChanged: {
                                            if (!pressed || !smartSlotEditMode || !slotOverlay.previewActive)
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
                                            if (!smartSlotEditMode || !slotOverlay.previewActive)
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
                                            slotOverlay.previewActive = false
                                            window.clearSlotPreview()
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
                                        delegate: Rectangle {
                                            required property var modelData
                                            objectName: "smartSlotHandle-" + String(modelData.dir) + "-" + String(slotOverlay.modelData.id || "")
                                            visible: smartSlotEditMode && slotOverlay.isSelectedSlot
                                            width: 11; height: 11; radius: 2
                                            x: modelData.fx * slotOverlay.width - width / 2
                                            y: modelData.fy * slotOverlay.height - height / 2
                                            color: "white"
                                            border.width: 2
                                            border.color: "#0F5BD8"
                                            z: 10
                                            MouseArea {
                                                id: slotResizeArea
                                                objectName: "smartSlotResizeArea-" + String(modelData.dir) + "-" + String(slotOverlay.modelData.id || "")
                                                anchors.fill: parent
                                                cursorShape: modelData.cursor
                                                preventStealing: true
                                                property real startGlobalX: 0
                                                property real startGlobalY: 0
                                                property real startX: 0
                                                property real startY: 0
                                                property real startW: 0
                                                property real startH: 0
                                                function resizedBounds(px, py) {
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
                                                    slotOverlay.queuePreview(resizedBounds(point.x, point.y), false)
                                                }
                                                onReleased: {
                                                    if (!slotOverlay.previewActive)
                                                        return
                                                    var point = mapToItem(sheet, mouse.x, mouse.y)
                                                    slotOverlay.commitPreview(resizedBounds(point.x, point.y), "resize")
                                                }
                                                onCanceled: {
                                                    slotOverlay.previewActive = false
                                                    window.clearSlotPreview()
                                                    previewTimer.stop()
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Item {
                                id: selectionOverlay
                                visible: !smartSlotEditMode && anchorNode && page && effectiveVisible(anchorNode)
                                x: visible ? anchorNode.transform.x * zoom : 0
                                y: visible ? anchorNode.transform.y * zoom : 0
                                width: visible ? Math.max(1, anchorNode.transform.width * zoom) : 1
                                height: visible ? Math.max(1, anchorNode.transform.height * zoom) : 1
                                rotation: visible ? Number(anchorNode.transform.rotation || 0) : 0
                                z: 200000

                                Rectangle { anchors.fill: parent; color: "transparent"; border.width: 2; border.color: "#0F5BD8" }
                                Rectangle { x: parent.width / 2; y: -30; width: 1; height: 30; color: "#0F5BD8" }
                                Rectangle {
                                    id: rotateHandle
                                    width: 13
                                    height: 13
                                    radius: 7
                                    x: parent.width / 2 - 6.5
                                    y: -42
                                    color: "white"
                                    border.width: 2
                                    border.color: "#0F5BD8"
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
                SplitView.preferredWidth: 300
                SplitView.minimumWidth: 265
                color: "#FFFFFF"
                border.color: "#D9E2EF"

                ScrollView {
                    anchors.fill: parent
                    clip: true
                    ColumnLayout {
                        width: parent.width
                        spacing: 10
                        anchors.margins: 14

                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Propriedades"; font.bold: true; font.pixelSize: 14; color: "#16213C" }
                            Item { Layout.fillWidth: true }
                            Label { text: anchorNode ? ("ID: " + String(anchorNode.id).slice(0, 8)) : "Nenhum item"; font.pixelSize: 9; color: "#8995AC" }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#EDF0F5" }
                        Label { text: "Nome do elemento"; color: "#606C84"; font.pixelSize: 10 }
                        Label { id: inspectorName; text: "Nada selecionado"; color: "#293957"; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight; padding: 9; background: Rectangle { color: "#FAFBFE"; radius: 6; border.color: "#DDE4F0" } }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: "#E6EAF2"
                        }
                        Label { text: sceneBridge.status; color: "#64748B"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#E6ECF4" }

                        ColumnLayout {
                            visible: anchorNode && (anchorNode.kind === "image" || anchorNode.kind === "background")
                            Layout.fillWidth: true
                            spacing: 7
                            Label { text: "Imagem selecionada"; font.bold: true; color: "#334155" }
                            Button { text: "Substituir imagem"; Layout.fillWidth: true; onClicked: replaceSelectedImageDialog.open() }
                            Button { text: "Remover fundo"; Layout.fillWidth: true; onClicked: removeCurrentBackground() }
                            RowLayout {
                                Label { text: "Ajuste"; color: "#475569" }
                                ComboBox {
                                    Layout.fillWidth: true
                                    model: ["contain","cover","fill"]
                                    onActivated: if (anchorNode) sceneBridge.dispatch(JSON.stringify({"name":"crop","node_id":anchorNode.id,"fit":currentText}))
                                }
                            }
                        }
                        ColumnLayout {
                            visible: anchorNode && anchorNode.kind === "text"
                            Layout.fillWidth: true
                            Label { text: "Texto"; color: "#475569"; font.bold: true }
                            TextArea { id: textEditor; Layout.fillWidth: true; Layout.preferredHeight: 90; wrapMode: TextEdit.Wrap }
                            Button { text: "Aplicar texto"; Layout.fillWidth: true; onClicked: if (anchorNode) sceneBridge.editText(anchorNode.id, textEditor.text) }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: "#E6ECF4" }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 116
            radius: 12
            color: "#FFFFFF"
            border.color: "#E4E9F4"
            RowLayout {
                anchors.fill: parent
                anchors.margins: 13
                spacing: 12
                Repeater {
                    model: scene.pages || []
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        Layout.preferredWidth: 76
                        Layout.preferredHeight: 92
                        radius: 8
                        color: "#FDFEFF"
                        border.color: modelData.id === scene.active_page_id ? "#365CFF" : "#E2E7F2"
                        border.width: modelData.id === scene.active_page_id ? 2 : 1
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 4
                            spacing: 3
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                color: modelData.background || "#FFFFFF"
                                border.color: "#DCE3EF"
                                clip: true
                                // Miniature representation uses actual document node colors.
                                Repeater {
                                    model: Object.values(modelData.nodes || {}).slice(0, 28)
                                    delegate: Rectangle {
                                        required property var modelData
                                        visible: modelData.visible !== false
                                        x: Math.max(0, Number(modelData.transform.x) / Math.max(1, page ? page.width : 1080) * parent.width)
                                        y: Math.max(0, Number(modelData.transform.y) / Math.max(1, page ? page.height : 1350) * parent.height)
                                        width: Math.max(1, Number(modelData.transform.width) / Math.max(1, page ? page.width : 1080) * parent.width)
                                        height: Math.max(1, Number(modelData.transform.height) / Math.max(1, page ? page.height : 1350) * parent.height)
                                        color: modelData.kind === "image" ? "#E1EAF8" : (modelData.style ? modelData.style.fill || "#EBEFF7" : "#EBEFF7")
                                    }
                                }
                            }
                            Label {
                                text: modelData.name || ("Página " + (index + 1))
                                Layout.alignment: Qt.AlignHCenter
                                font.pixelSize: 9
                                color: modelData.id === scene.active_page_id ? "#2954F9" : "#79849D"
                            }
                        }
                        MouseArea { anchors.fill: parent; onClicked: sceneBridge.dispatch(JSON.stringify({"name":"select_page","page_id":modelData.id})) }
                    }
                }
                Rectangle {
                    Layout.preferredWidth: 77
                    Layout.preferredHeight: 92
                    radius: 8
                    color: "#FBFCFF"
                    border.color: "#CBD7EB"
                    border.width: 1
                    ColumnLayout {
                        anchors.centerIn: parent
                        Label { text: "+"; Layout.alignment: Qt.AlignHCenter; font.pixelSize: 25; color: "#425276" }
                        Label { text: "Adicionar página"; Layout.alignment: Qt.AlignHCenter; font.pixelSize: 9; color: "#71809E" }
                    }
                    MouseArea { anchors.fill: parent; onClicked: sceneBridge.dispatch('{"name":"add_page"}') }
                }
                Item { Layout.fillWidth: true }
                ToolButton { text: "▦"; checkable: true; checked: showGrid; onClicked: showGrid = checked; ToolTip.text: "Grade"; ToolTip.visible: hovered }
                Label {
                    visible: productDragActive
                    text: dragHoverSlotId ? "Solte para aplicar o produto" : "Arraste sobre um card"
                    color: dragHoverSlotId ? "#16A34A" : "#2954F9"
                    font.pixelSize: 10
                    font.bold: true
                }
                ToolButton { text: "◉"; checkable: true; checked: showRulers; onClicked: showRulers = checked; ToolTip.text: "Réguas"; ToolTip.visible: hovered }
                Slider {
                    from: 0.12
                    to: 3.5
                    value: window.zoom
                    Layout.preferredWidth: 120
                    onMoved: window.zoom = value
                }
                Label { text: Math.round(window.zoom * 100) + "%"; Layout.preferredWidth: 44; color: "#17213E"; font.bold: true; font.pixelSize: 12; horizontalAlignment: Text.AlignRight }
                ToolButton {
                    text: "⛶"
                    ToolTip.text: "Ajustar zoom à página"; ToolTip.visible: hovered
                    onClicked: if (page) zoom = Math.max(0.12, Math.min(3.5,
                        Math.min((workspace.width - 180) / page.width, (workspace.height - 140) / page.height)))
                }
            }
        }
    }

    Rectangle {
        id: productDragGhost
        visible: productDragActive && !!draggedProduct
        x: productDragX - width / 2
        y: productDragY - height / 2
        width: 250
        height: 74
        z: 1000000
        radius: 8
        color: "#FFFFFFF4"
        border.width: 2
        border.color: dragHoverSlotId ? "#16A34A" : "#0F5BD8"
        opacity: 0.94

        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 9
            Rectangle {
                Layout.preferredWidth: 54
                Layout.preferredHeight: 54
                radius: 5
                color: "#F8FAFC"
                border.color: "#E5EAF1"
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
                Label { Layout.fillWidth: true; text: productLabel(draggedProduct); color: "#111827"; font.bold: true; font.pixelSize: 11; elide: Text.ElideRight }
                Label { text: dragHoverSlotId ? "Soltar no card" : "Arraste até um Smart Slot"; color: dragHoverSlotId ? "#16A34A" : "#0F5BD8"; font.bold: true; font.pixelSize: 10 }
            }
        }
    }
}