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
    property real productSidebarWidth: sceneBridge.productSidebarWidth
    property string imageMatchReport: ""
    // Beta 42: studio navigation mirrors the supplied SR Studio 5.0 reference.
    property int studioSection: 0
    property int studioNavigation: 2
    property int autoLayoutVariation: 0
    property string productQuery: ""
    property string productFilter: "Todos os produtos"
    // ListView virtualizes delegates, so all spreadsheet products remain scrollable.
    property var imageBankInventory: ({"images":[],"counts":{}})
    property var imageReviewStates: ({})
    property int reviewProductCount: 0
    property var imageBankSuggestions: []
    property var imageBankScores: ({})
    property string imageBankQuery: ""
    property string imageBankStatus: "Todos"
    property string imageBankTargetProductId: ""
    property string imageBankTargetProductName: ""
    property bool showProductImageReview: false
    property bool imageBankShowAll: false
    property var bankSelectedImage: null
    property var bankReviewQueue: []
    property bool bankDownloadStarted: false

    function openImageReviewFor(product) {
        studioSection = 0
        var p = product || ({})
        imageBankTargetProductId = String(p.id || p.product_id || "")
        imageBankTargetProductName = String(p.name || p.display_name || p.original_name || "")
        imageBankQuery = ""
        imageBankShowAll = false
        showProductImageReview = true
        refreshImageBank()
        Qt.callLater(function() {
            var choices = imageBankTargetCombo.model || []
            for (var i = 0; i < choices.length; ++i) {
                if (String(choices[i].id || "") === imageBankTargetProductId) {
                    imageBankTargetCombo.currentIndex = i
                    break
                }
            }
        })
    }

    function plainBankName(value) {
        return String(value || "").toUpperCase()
            .replace(/[ÁÀÂÃÄ]/g, "A").replace(/[ÉÈÊË]/g, "E")
            .replace(/[ÍÌÎÏ]/g, "I").replace(/[ÓÒÔÕÖ]/g, "O")
            .replace(/[ÚÙÛÜ]/g, "U").replace(/Ç/g, "C")
    }

    function bankSuggestionScore(entry) {
        return Number(imageBankScores[String(entry.id || "")] || 0)
    }

    // The bank is internal; only linked spreadsheet products are shown in Produtos.

    function refreshImageBank() {
        try {
            imageBankInventory = JSON.parse(sceneBridge.imageBankJson())
            imageReviewStates = JSON.parse(sceneBridge.imageReviewStatesJson())
            reviewProductCount = products().length
            refreshImageSuggestions()
        } catch (error) {
            imageBankInventory = {"images":[], "counts":{}, "error":String(error)}
        }
    }

    function refreshImageSuggestions() {
        imageBankSuggestions = imageBankTargetProductId ?
            JSON.parse(sceneBridge.imageSuggestionsJson(imageBankTargetProductId)) : []
        var scores = ({})
        for (var i = 0; i < imageBankSuggestions.length; ++i)
            scores[String(imageBankSuggestions[i].id || "")] = imageBankSuggestions[i].score
        imageBankScores = scores
    }

    function filteredBankImages() {
        var text = imageBankQuery.toLocaleLowerCase().trim()
        var entries = imageBankShowAll ? (imageBankInventory.images || []) : imageBankSuggestions
        if (!imageBankTargetProductId)
            return []
        return entries.filter(function(entry) {
            var matches = !text || (String(entry.name || "") + " " + String(entry.product_id || "")
                        + " " + String(entry.source || "")).toLocaleLowerCase().indexOf(text) >= 0
            var filter = imageBankStatus === "Todos" ||
                (imageBankStatus === "Aprovadas" && entry.status === "approved") ||
                (imageBankStatus === "Pendentes" && entry.status === "pending") ||
                (imageBankStatus === "Vinculadas" && entry.status === "manual")
            var allowedKind = entry.kind === "product" || entry.kind === "unknown"
            return matches && filter && allowedKind &&
                (imageBankShowAll || bankSuggestionScore(entry) > 0)
        }).sort(function(a, b) { return bankSuggestionScore(b) - bankSuggestionScore(a) })
    }

    property bool showProductionGate: false
    property bool showAdvancedSlotActions: false

    function productImageState(p) {
        return imageReviewStates[String(p.id || p.product_id || "")] ||
            ((p.image_path || p.image) ? "linked" : "missing")
    }

    function filteredProducts() {
        var query = productQuery.toLocaleLowerCase().trim()
        return products().filter(function(p) {
            var searchable = (productLabel(p) + " " + String(p.id || p.product_id || "")).toLocaleLowerCase()
            var state = productImageState(p)
            return (!query || searchable.indexOf(query) !== -1)
                && (productFilter === "Todos os produtos"
                    || (productFilter === "Com imagem" && state === "linked")
                    || (productFilter === "Aguardando confirmação" && state === "pending")
                    || (productFilter === "Sem imagem disponível" && state === "missing"))
        })
    }

    function createBlueSlot(dropX, dropY) {
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
            "name": "add_item_slot", "preset_id": "limpeza-blue-v1",
            "x": dropX === undefined ? null : dropX,
            "y": dropY === undefined ? null : dropY
        })))
        if (result.ok && result.payload) {
            selectedSlotId = String(result.payload.slot_id || "")
            smartSlotEditMode = true
            smartSlotInspectionMode = true
        }
    }

    function createIndividualSlot(dropX, dropY) {
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
            "name": "add_item_slot", "preset_id": "individual-beta44",
            "x": dropX === undefined ? null : dropX,
            "y": dropY === undefined ? null : dropY
        })))
        if (result.ok && result.payload) {
            selectedSlotId = String(result.payload.slot_id || "")
            smartSlotEditMode = true
            smartSlotInspectionMode = true
        }
    }

    function createMultiSlot(count, dropX, dropY) {
        var modes = ["auto", "one", "two"]
        var mode = modes[slotPriceMode.currentIndex] || "auto"
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
            "name": "add_multi_item_slot", "count": count, "price_mode": mode,
            "x": dropX === undefined ? null : dropX,
            "y": dropY === undefined ? null : dropY
        })))
        if (result.ok && result.payload) {
            var created = result.payload.slot_ids || []
            selectedSlotId = created.length ? String(created[0]) : ""
            smartSlotEditMode = true
            smartSlotInspectionMode = true
        }
    }

    function placeSlotAt(kind, sourceItem, mouseX, mouseY) {
        if (!page || !sheet)
            return
        var point = sourceItem.mapToItem(sheet, mouseX, mouseY)
        var docX = point.x / zoom
        var docY = point.y / zoom
        if (docX < 0 || docY < 0 || docX > page.width || docY > page.height)
            return
        var w = kind === "blue" ? 418 : (kind === "individual" ? 460 : page.width * .94)
        var h = kind === "blue" ? 320 : (kind === "individual" ? 490 :
                     Math.min(page.height * .31, 315, w / 4.75))
        var px = Math.max(0, Math.min(page.width - w, docX - w / 2))
        var py = Math.max(0, Math.min(page.height - h, docY - h / 2))
        if (kind === "blue")
            createBlueSlot(px, py)
        else if (kind === "individual")
            createIndividualSlot(px, py)
        else
            createMultiSlot(kind === "multi5" ? 5 : 6, px, py)
    }

    function duplicateSelectedSmartSlot() {
        if (!selectedSlotId)
            return
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
            "name":"duplicate_slot", "slot_id":selectedSlotId
        })))
        if (result.ok && result.payload && result.payload.slot_ids.length)
            selectedSlotId = String(result.payload.slot_ids[0])
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
        title: "Excel mantém o encarte · PPTX substitui o layout"
        nameFilters: ["Excel/Canva (*.xlsx *.xlsm *.pptx)", "Produtos Excel (*.xlsx *.xlsm)", "Modelos PPTX (*.pptx)"]
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
    // Bitmap miniatures rendered by the SAME Python/Qt slot constructors
    // used on the scene canvas; no placeholder QML designs.
    property var slotPreviewCatalog: sceneBridge && sceneBridge.slotPreviewsJson
                                     ? JSON.parse(sceneBridge.slotPreviewsJson) : ({})
    property string selectedSlotId: ""
    property var campaignIds: ["terca-verde", "quarta-cafe", "quinta-file", "churrasco"]
    function campaignArtworkList(kind) {
        var items = scene && scene.editor && scene.editor.campaign_assets
                    ? scene.editor.campaign_assets : []
        var campaign = window.campaignIds[campaignCampaignChoice.currentIndex]
        return items.filter(function(entry) {
            return entry.kind === kind && entry.campaign_id === campaign
                   && entry.source === "builtin"
        })
    }
    function applyInstalledCampaignArt(kind, index) {
        var items = campaignArtworkList(kind)
        if (index < 0 || index >= items.length)
            return
        sceneBridge.dispatch(JSON.stringify(kind === "background"
            ? {"name":"apply_campaign_preset", "background_id":items[index].id}
            : {"name":"apply_campaign_seal", "seal_id":items[index].id}))
    }
    property var inspectorProduct: null
    property bool slotDragActive: false
    property string slotDragKey: ""
    property real slotDragX: 0
    property real slotDragY: 0
    property string inspectorStatus: ""
    property string pendingImageProductId: ""
    property string pendingImageProductName: ""
    FileDialog {
        id: productImageDialog
        title: "Adicionar imagem ao produto"
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)"]
        onAccepted: sceneBridge.attachProductImage(window.pendingImageProductId, window.pendingImageProductName, selectedFile.toString())
    }
    FileDialog {
        id: campaignPackDialog
        title: "Importar pacote de campanhas do SR Studio"
        nameFilters: ["Pacote ZIP de campanhas (*.zip)"]
        onAccepted: sceneBridge.dispatch(JSON.stringify({
            "name":"import_campaign_pack", "path":selectedFile.toString()
        }))
    }
    FileDialog {
        id: campaignBackgroundDialog
        title: "Selecionar fundo da campanha (sem preços nem datas fixos)"
        nameFilters: ["Imagens (*.jpg *.jpeg *.png *.webp)"]
        onAccepted: sceneBridge.dispatch(JSON.stringify({
            "name":"set_campaign_art", "kind":"background", "path":selectedFile.toString(),
            "campaign_id":window.campaignIds[campaignCampaignChoice.currentIndex]
        }))
    }
    FileDialog {
        id: campaignSealDialog
        title: "Selecionar logo ou selo da campanha"
        nameFilters: ["Selos (*.png *.webp *.jpg *.jpeg)"]
        onAccepted: sceneBridge.dispatch(JSON.stringify({
            "name":"set_campaign_art", "kind":"seal", "path":selectedFile.toString(),
            "campaign_id":window.campaignIds[campaignCampaignChoice.currentIndex]
        }))
    }
    FileDialog {
        id: historicalReviewZipDialog
        title: "Importar acervo histórico para revisão"
        nameFilters: ["Banco histórico ZIP (*.zip)"]
        onAccepted: sceneBridge.importHistoricalReviewZip(selectedFile.toString())
    }
    Dialog {
        id: bankReviewConfirm
        modal: true
        title: "Confirmar imagem da embalagem"
        width: 440
        height: 360
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            if (!imageBankTargetProductId || !bankSelectedImage)
                return
            sceneBridge.attachProductImage(
                imageBankTargetProductId, imageBankTargetProductName,
                localSource(bankSelectedImage.image_path))
        }
        ColumnLayout {
            anchors.fill: parent
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: "Produto: " + imageBankTargetProductName
                wrapMode: Text.WordWrap
                font.bold: true
                color: "#142D5B"
            }
            Image {
                Layout.fillWidth: true
                Layout.fillHeight: true
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                source: localSource(bankSelectedImage ? bankSelectedImage.image_path : "")
            }
            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                font.pixelSize: 11
                text: "Confira marca, sabor e tamanho. Ao confirmar, esta foto será salva para este código de produto e reutilizada nas próximas planilhas. Nenhuma outra foto será aprovada."
                color: "#7A4D0A"
            }
        }
    }
    Dialog {
        id: bankBatchConfirm
        modal: true
        title: "Revisar e confirmar imagens em lote"
        width: 530
        height: 510
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            sceneBridge.attachProductImagesBatch(JSON.stringify(bankReviewQueue))
            bankReviewQueue = []
        }
        ColumnLayout {
            anchors.fill: parent
            Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: "Confira visualmente cada embalagem, variação e código antes de confirmar."
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Column {
                    width: 480
                    spacing: 5
                    Repeater {
                        model: bankReviewQueue
                        delegate: Row {
                            required property var modelData
                            spacing: 8
                            Image {
                                width: 65; height: 70
                                source: localSource(modelData.image_path)
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                            }
                            Label {
                                width: 390
                                wrapMode: Text.WordWrap
                                text: String(modelData.name) + "\nCódigo: " + String(modelData.product_id)
                            }
                        }
                    }
                }
            }
        }
    }
    Connections {
        target: sceneBridge
        function onHistoricalImageBankDone(ok, detail) {
            bankDownloadStarted = false
            if (studioSection === 0 && showProductImageReview)
                refreshImageBank()
        }
        function onProductImageDone(ok, productId, payload, error) {
            if (studioSection === 0 && showProductImageReview)
                refreshImageBank()
        }
        function onProductImagesBatchDone(ok, payload, error) {
            if (studioSection === 0)
                refreshImageBank()
        }
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
        var rootId = slot.metadata ? String(slot.metadata.multi_parent_id || slot.metadata.root_node_id || "") : ""
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
        var rootId = slot.metadata ? String(slot.metadata.multi_parent_id || slot.metadata.root_node_id || "") : ""
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

    function selectedSmartSlot() {
        for (var i = 0; i < slots().length; ++i)
            if (slots()[i].id === selectedSlotId)
                return slots()[i]
        return null
    }

    function propertyProduct() {
        if (inspectorProduct)
            return inspectorProduct
        var slot = selectedSmartSlot()
        if (!slot)
            return null
        var p = slot.metadata ? slot.metadata.product_snapshot : null
        return p && Object.keys(p).length ? p : null
    }

    function refreshPropertyFields() {
        var product = propertyProduct()
        if (product) {
            inspectorProductName.text = product.display_name || product.name || product.original_name || ""
            inspectorPrice.text = String(product.price || "")
            inspectorAppPrice.text = String(product.app_price || product.club_price || "")
            inspectorUnit.text = String(product.unit || "UN")
        } else {
            inspectorProductName.text = ""
            inspectorPrice.text = ""
            inspectorAppPrice.text = ""
            inspectorUnit.text = "UN"
        }
    }

    function saveProductProperties() {
        var product = propertyProduct()
        if (!product)
            return
        var changes = {
            "display_name": inspectorProductName.text,
            "price": inspectorPrice.text,
            "app_price": inspectorAppPrice.text,
            "unit": inspectorUnit.text
        }
        var command
        if (inspectorProduct && String(product.id || product.product_id || "")) {
            command = {"name":"update_product_data",
                       "product_id":String(product.id || product.product_id),
                       "changes":changes, "cascade":true}
        } else {
            command = {"name":"update_product_fields",
                       "slot_id":selectedSlotId, "changes":changes}
        }
        var result = JSON.parse(sceneBridge.dispatch(JSON.stringify(command)))
        inspectorStatus = result.message || ""
    }

    onInspectorProductChanged: Qt.callLater(refreshPropertyFields)
    onSelectedSlotIdChanged: Qt.callLater(refreshPropertyFields)

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
        Qt.callLater(refreshPropertyFields)
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() {
            window.refreshScene()
            if (window.products().length !== reviewProductCount)
                Qt.callLater(window.refreshImageBank)
        }
    }

    Component.onCompleted: {
        refreshScene()
        syncInspector()
        Qt.callLater(refreshImageBank)
    }

    Shortcut { sequence: StandardKey.Undo; onActivated: sceneBridge.undo() }
    Shortcut { sequence: StandardKey.Redo; onActivated: sceneBridge.redo() }
    Shortcut { sequence: StandardKey.Delete; onActivated: sceneBridge.dispatch('{"name":"delete"}') }
    Timer {
        id: saveProductSidebarWidth
        interval: 650
        repeat: false
        onTriggered: sceneBridge.saveProductSidebarWidth(Math.round(window.productSidebarWidth))
    }

    Shortcut { sequence: "Ctrl+D"; onActivated: selectedSlotId ? duplicateSelectedSmartSlot() : sceneBridge.dispatch('{"name":"duplicate"}') }
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
                id: catalogSidebar
                SplitView.preferredWidth: studioSection === 0 ? window.productSidebarWidth : 332
                SplitView.minimumWidth: 340
                SplitView.maximumWidth: 565
                onWidthChanged: {
                    if (studioSection === 0 && width >= 340 && width <= 565
                            && Math.abs(width - window.productSidebarWidth) >= 2) {
                        window.productSidebarWidth = width
                        saveProductSidebarWidth.restart()
                    }
                }
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
                                    { icon:"⬡", title:"Produtos", section:0 }, { icon:"⬡", title:"Slots", section:1 },
                                    { icon:"♧", title:"Layouts", section:2 },
                                    { icon:"T", title:"Texto", section:4 }, { icon:"♧", title:"Formas", section:5 },
                                    { icon:"▨", title:"Fundos", section:6 }, { icon:"▱", title:"Camadas", section:7 },
                                    { icon:"☷", title:"Projeto", section:8 }
                                ]
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 73
                                    Layout.leftMargin: 5
                                    Layout.rightMargin: 5
                                    radius: 9
                                    color: studioSection === modelData.section ? "#EFF3FF" : "transparent"
                                    ColumnLayout {
                                        anchors.centerIn: parent
                                        spacing: 5
                                        Label { text: modelData.icon; Layout.alignment: Qt.AlignHCenter; color: studioSection === modelData.section ? "#2C4BFA" : "#4C577F"; font.pixelSize: 24 }
                                        Label { text: modelData.title; Layout.alignment: Qt.AlignHCenter; color: studioSection === index ? "#284DFF" : "#425072"; font.pixelSize: 9; font.bold: studioSection === modelData.section }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: studioSection = modelData.section }
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
                                text: (studioSection === 0 && showProductImageReview) ? "Banco SR · Produtos" :
                                      ["Produtos","Slots","Layouts de Promoção","","Texto","Formas","Fundos","Camadas","Projeto"][studioSection]
                                color: "#111B38"; font.pixelSize: 15; font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            ToolButton {
                                text: showProductImageReview ? "← Produtos" : "⌄"
                                onClicked: {
                                    if (showProductImageReview)
                                        showProductImageReview = false
                                    else
                                        studioSection = 0
                                }
                            }
                        }
                        ColumnLayout {
                            Layout.fillHeight: true
                            Layout.fillWidth: true
                            visible: studioSection === 0 && !showProductImageReview
                            spacing: 11
                            RowLayout {
                                Layout.fillWidth: true
                                TextField { Layout.fillWidth: true; placeholderText: "⌕  Buscar produtos..."; text: productQuery; onTextChanged: productQuery = text; font.pixelSize: 11 }
                                ToolButton { text: "▽"; onClicked: productFilter = productFilter === "Sem imagem" ? "Todos os produtos" : "Sem imagem" }
                            }
                            ComboBox {
                                Layout.fillWidth: true
                                model: ["Todos os produtos","Com imagem","Aguardando confirmação","Sem imagem disponível"]
                                onActivated: productFilter = currentText
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: {
                                        var all = products()
                                        var count = all.filter(function(p) { return !!(p.image_path || p.image) }).length
                                        return "Fotos encontradas: " + count + " / " + all.length
                                    }
                                    color: "#536783"; font.pixelSize: 11
                                }
                                ToolButton {
                                    text: "↻ Fotos"
                                    ToolTip.text: "Reconsultar o banco de imagens aprovado"
                                    ToolTip.visible: hovered
                                    onClicked: sceneBridge.refreshProductImages()
                                }
                                ToolButton {
                                    text: "Banco SR"
                                    ToolTip.text: "Buscar, recuperar e confirmar fotos apenas para produtos desta planilha"
                                    ToolTip.visible: hovered
                                    onClicked: window.openImageReviewFor(window.inspectorProduct)
                                }
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
                                    height: Math.max(122, productInformation.implicitHeight + 28)
                                    radius: 11
                                    color: productMouse.containsMouse ? "#F1F6FF" : "#FFFFFF"
                                    border.color: productMouse.dragging ? "#2869EF" : "#DCE5F1"
                                    border.width: productMouse.dragging ? 2 : 1
                                    property var productData: modelData
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 11
                                        spacing: 10
                                        Rectangle {
                                            Layout.preferredWidth: 84
                                            Layout.preferredHeight: 96
                                            Layout.alignment: Qt.AlignVCenter
                                            radius: 8
                                            color: "#F8FAFE"
                                            border.color: "#E8EEF6"
                                            Image {
                                                anchors.fill: parent
                                                anchors.margins: 3
                                                source: localSource(modelData.image_path || modelData.image || "")
                                                fillMode: Image.PreserveAspectFit
                                                asynchronous: true
                                                cache: true
                                                smooth: true
                                            }
                                        }
                                        ColumnLayout {
                                            id: productInformation
                                            Layout.fillWidth: true
                                            Layout.alignment: Qt.AlignVCenter
                                            spacing: 3
                                            Label {
                                                Layout.fillWidth: true
                                                text: modelData.display_name || modelData.name || modelData.original_name || "Produto"
                                                color: "#11234A"
                                                font.bold: true
                                                font.pixelSize: 13
                                                wrapMode: Text.WordWrap
                                                elide: Text.ElideNone
                                            }
                                            Label {
                                                text: String(modelData.unit || "UN").toUpperCase()
                                                color: "#7886A0"; font.pixelSize: 11
                                            }
                                            Label {
                                                text: productImageState(modelData) === "linked" ? "Com imagem" :
                                                      productImageState(modelData) === "pending" ? "Aguardando confirmação" :
                                                      "Sem imagem disponível"
                                                color: productImageState(modelData) === "linked" ? "#12805C" :
                                                       productImageState(modelData) === "pending" ? "#9A6700" : "#64748B"
                                                font.pixelSize: 10
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                text: modelData.price ? ("Oferta  R$ " + String(modelData.price).replace(".", ",")) : "Sem preço"
                                                color: "#1154D8"; font.bold: true; font.pixelSize: 14
                                            }
                                            Label {
                                                Layout.fillWidth: true
                                                visible: !!(modelData.app_price || modelData.club_price ||
                                                            modelData.wholesale_price || modelData.retail_price)
                                                text: {
                                                    var extra = modelData.app_price || modelData.club_price ||
                                                                modelData.wholesale_price || modelData.retail_price
                                                    var label = (modelData.app_price || modelData.club_price) ? "Clube SR  " :
                                                                (modelData.wholesale_price ? "Atacado  " : "Varejo  ")
                                                    return label + "R$ " + String(extra || "").replace(".", ",")
                                                }
                                                color: "#B32D18"; font.bold: true; font.pixelSize: 13
                                            }
                                        }
                                        ToolButton {
                                            text: "+"
                                            font.pixelSize: 18
                                            z: 3
                                            Layout.preferredWidth: 26
                                            Layout.preferredHeight: 32
                                            onClicked: {
                                                window.inspectorProduct = productCard.productData
                                                if (selectedSlotId)
                                                    bindProduct(modelData)
                                            }
                                            ToolTip.visible: hovered
                                            ToolTip.text: selectedSlotId ? "Aplicar ao Smart Slot selecionado" : "Selecione um slot antes de aplicar"
                                        }
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
                                            window.inspectorProduct = productCard.productData
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
                                                text: "Buscar foto no Banco SR"
                                                onTriggered: window.openImageReviewFor(productCard.productData)
                                            }
                                            MenuItem {
                                                text: "Adicionar ou substituir imagem"
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
                                Label {
                                    anchors.centerIn: parent
                                    visible: productList.count === 0
                                    text: "Importe uma planilha para carregar produtos."
                                    width: productList.width - 30
                                    wrapMode: Text.WordWrap
                                    horizontalAlignment: Text.AlignHCenter
                                    color: "#94A3B8"
                                }
                            }
                        }
                        ColumnLayout {
                            Layout.fillHeight: true
                            Layout.fillWidth: true
                            visible: studioSection === 0 && showProductImageReview
                            spacing: 8
                            Label {
                                Layout.fillWidth: true
                                text: "Banco de Imagens SR"
                                color: "#173D72"; font.bold: true; font.pixelSize: 14
                            }
                            Label {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                color: "#64748B"; font.pixelSize: 10
                                text: "Aprovadas: " + Number(imageBankInventory.counts.approved || 0)
                                    + "  ·  Pendentes: " + Number(imageBankInventory.counts.pending || 0)
                                    + "  ·  Vinculadas: " + Number(imageBankInventory.counts.manual || 0)
                            }
                            Label {
                                visible: !!imageBankInventory.error
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                color: "#B91C1C"; font.pixelSize: 10
                                text: String(imageBankInventory.error || "")
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                TextField {
                                    Layout.fillWidth: true
                                    placeholderText: "Buscar imagens ou códigos..."
                                    text: imageBankQuery
                                    onTextChanged: imageBankQuery = text
                                    font.pixelSize: 11
                                }
                                ToolButton {
                                    text: "⟳"
                                    ToolTip.text: "Atualizar banco local"
                                    ToolTip.visible: hovered
                                    onClicked: refreshImageBank()
                                }
                            }
                            ComboBox {
                                Layout.fillWidth: true
                                model: ["Todos", "Aprovadas", "Pendentes", "Vinculadas"]
                                onActivated: imageBankStatus = currentText
                            }
                            Label {
                                Layout.fillWidth: true
                                text: "Escolha um produto da planilha para revisar as fotos:"
                                font.pixelSize: 10; color: "#64748B"
                            }
                            ComboBox {
                                id: imageBankTargetCombo
                                Layout.fillWidth: true
                                model: [{"label":"Selecione um produto...", "id":"", "name":""}]
                                    .concat(products().map(function(p) {
                                        return {"label":productLabel(p),
                                                "id":String(p.id || p.product_id || ""),
                                                "name":String(p.name || p.display_name || p.original_name || "")}
                                    }))
                                textRole: "label"; valueRole: "id"
                                onActivated: {
                                    var data = model[currentIndex] || {}
                                    imageBankTargetProductId = String(data.id || "")
                                    imageBankTargetProductName = String(data.name || data.label || "")
                                    refreshImageSuggestions()
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                color: "#64748B"; font.pixelSize: 10
                                text: "Somente fotos do produto selecionado são sugeridas. As pendentes exigem sua confirmação após conferir a embalagem."
                            }
                            Button {
                                Layout.fillWidth: true
                                text: "Revisar lote (" + bankReviewQueue.length + ")"
                                enabled: bankReviewQueue.length > 0
                                onClicked: bankBatchConfirm.open()
                            }
                            CheckBox {
                                Layout.fillWidth: true
                                enabled: !!imageBankTargetProductId
                                text: "Procurar também entre outras fotos do banco"
                                checked: imageBankShowAll
                                onToggled: imageBankShowAll = checked
                            }
                            ListView {
                                id: imageBankList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 7
                                model: filteredBankImages()
                                ScrollBar.vertical: ScrollBar {}
                                delegate: Rectangle {
                                    required property var modelData
                                    width: imageBankList.width - 4
                                    height: 158
                                    radius: 8
                                    color: "#FFFFFF"
                                    border.color: "#D9E4F2"
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 7
                                        spacing: 7
                                        Rectangle {
                                            Layout.preferredWidth: 73
                                            Layout.preferredHeight: 135
                                            radius: 5; color: "#F8FAFC"
                                            border.color: "#E5EAF1"
                                            Image {
                                                anchors.fill: parent
                                                anchors.margins: 3
                                                source: localSource(modelData.image_path)
                                                fillMode: Image.PreserveAspectFit
                                                asynchronous: true
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 3
                                            Label {
                                                Layout.fillWidth: true
                                                text: String(modelData.name || "Imagem")
                                                font.pixelSize: 11; font.bold: true
                                                elide: Text.ElideRight
                                                color: "#17213E"
                                            }
                                            Label {
                                                text: modelData.status === "pending" ? "PENDENTE · Confirmar embalagem" :
                                                      modelData.status === "approved" ? "APROVADA" : "VINCULADA"
                                                color: modelData.status === "pending" ? "#9A6700" : "#12805C"
                                                font.pixelSize: 9
                                            }
                                            Label {
                                                text: String(modelData.source || "")
                                                color: "#64748B"; font.pixelSize: 9
                                            }
                                            Label {
                                                visible: !!modelData.reason
                                                text: String(modelData.reason || "")
                                                color: "#284F8F"; font.pixelSize: 9
                                            }
                                            Button {
                                                text: "Conferir e vincular"
                                                Layout.fillWidth: true
                                                font.pixelSize: 10
                                                enabled: !!imageBankTargetProductId
                                                onClicked: {
                                                    bankSelectedImage = modelData
                                                    bankReviewConfirm.open()
                                                }
                                            }
                                            Button {
                                                text: "Adicionar ao lote"
                                                Layout.fillWidth: true
                                                font.pixelSize: 10
                                                enabled: !!imageBankTargetProductId
                                                onClicked: {
                                                    var next = bankReviewQueue.filter(function(item) {
                                                        return item.product_id !== imageBankTargetProductId
                                                    })
                                                    next.push({"product_id":imageBankTargetProductId,
                                                               "name":imageBankTargetProductName,
                                                               "image_path":modelData.image_path})
                                                    bankReviewQueue = next
                                                }
                                            }
                                        }
                                    }
                                }
                                Label {
                                    anchors.centerIn: parent
                                    visible: imageBankList.count === 0
                                    width: imageBankList.width - 20
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 11; color: "#64748B"
                                    text: !imageBankTargetProductId ?
                                          "Selecione um produto da planilha acima." :
                                          !imageBankShowAll ?
                                          "Nenhuma correspondência sugerida. Marque 'Procurar também entre outras fotos' para examinar o acervo e conferir manualmente a embalagem." :
                                          "Nenhuma foto disponível neste filtro. Use Baixar acervo histórico ou importe seu ZIP."
                                }
                            }
                            Button {
                                Layout.fillWidth: true
                                text: bankDownloadStarted ? "Recuperando acervo..." : "Baixar acervo histórico verificado (36 MB)"
                                enabled: !bankDownloadStarted
                                onClicked: {
                                    bankDownloadStarted = true
                                    sceneBridge.downloadHistoricalReviewBank()
                                }
                            }
                            Button {
                                Layout.fillWidth: true
                                text: "Importar ZIP histórico já baixado"
                                onClicked: historicalReviewZipDialog.open()
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Button {
                                    Layout.fillWidth: true
                                    text: "Abrir pasta do Banco SR"
                                    onClicked: sceneBridge.openImageBankFolder()
                                }
                                Button {
                                    text: "Atualizar"
                                    onClicked: refreshImageBank()
                                }
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
                                Label { text: "Organiza Smart Slots reais da página, sem apagar produtos."; color: "#64748B"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Logo (%)"; color: "#425072" }
                                    SpinBox { id: logoReservePercent; from: 15; to: 50; value: 24; editable: true; Layout.fillWidth: true }
                                }
                                ComboBox {
                                    id: layoutPriceMode
                                    Layout.fillWidth: true
                                    model: ["Preços automáticos", "Um preço", "Dois preços"]
                                }
                                Repeater {
                                    model: [
                                        {"label":"Destaque individual", "mode":"individual"},
                                        {"label":"11 produtos", "mode":"eleven"},
                                        {"label":"9 produtos · Terça Verde", "mode":"nine"},
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

                                            Image {
                                                anchors.fill: parent
                                                source: window.slotPreviewCatalog["layout-" + previewLayoutCard.modelData.mode] || ""
                                                fillMode: Image.PreserveAspectFit
                                                asynchronous: true
                                                cache: false
                                                smooth: true
                                            }
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: sceneBridge.dispatch(JSON.stringify({
                                                "name":"apply_promotion_layout", "reuse_existing":true,
                                                "mode":previewLayoutCard.modelData.mode,
                                                "logo_reserved":logoReservePercent.value / 100,
                                                "price_mode":["auto","one","two"][layoutPriceMode.currentIndex]
                                            }))
                                        }
                                    }
                                }
                                Label { text: "Tema para os layouts"; color: "#284F8F"; font.bold: true }
                                Label { text: "O layout reutiliza os Smart Slots reais, sem criar novas famílias."; color: "#64748B"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Button {
                                    Layout.fillWidth: true; text: "Cor da campanha selecionada · página inteira"
                                    onClicked: sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_slot_theme", "theme":window.campaignIds[campaignCampaignChoice.currentIndex], "entire_page":true
                                    }))
                                }
                                Label { text: "Auto Layout"; color: "#284F8F"; font.bold: true }
                                SpinBox { id: autoLayoutCount; from: 1; to: 24; value: 6; editable: true; Layout.fillWidth: true }
                                Button {
                                    Layout.fillWidth: true
                                    text: "Criar Auto Layout"
                                    onClicked: sceneBridge.dispatch(JSON.stringify({
                                        "name":"apply_promotion_layout", "reuse_existing":true,
                                        "mode":"auto",
                                        "count":autoLayoutCount.value,
                                        "variation":window.autoLayoutVariation++,
                                        "logo_reserved":logoReservePercent.value / 100,
                                        "price_mode":["auto","one","two"][layoutPriceMode.currentIndex]
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
                                Button { text: "+ Slot Único"; Layout.fillWidth: true; onClicked: createBlueSlot() }
                                Button { text: "Ajustar Smart Slots"; Layout.fillWidth: true; checkable: true; checked: smartSlotEditMode; onClicked: { smartSlotEditMode = checked; smartSlotInspectionMode = checked } }
                                Button { text: "Copiar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"copy"}') }
                                Button { text: "Colar"; Layout.fillWidth: true; onClicked: sceneBridge.dispatch('{"name":"paste"}') }
                                Button { text: "Salvar"; Layout.fillWidth: true; onClicked: saveProjectDialog.open() }
                                Button { text: "Recuperar"; Layout.fillWidth: true; onClicked: sceneBridge.recoverLatest() }
                                Button {
                                    text: "Importar PPTX / Planilha"
                                    Layout.fillWidth: true
                                    onClicked: sourceImportDialog.open()
                                    ToolTip.visible: hovered
                                    ToolTip.text: "XLSX/XLSM adiciona produtos sem apagar o encarte; PPTX troca o layout."
                                }
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

                            Repeater {
                                model: [
                                    {"key":"blue", "label":"Slot Único", "count":0},
                                    {"key":"individual", "label":"Smart Slot Individual", "count":0},
                                    {"key":"multi5", "label":"Multi Itens — 5 produtos", "count":5},
                                    {"key":"multi6", "label":"Multi Itens — 6 produtos", "count":6}
                                ]
                                delegate: Rectangle {
                                    id: canonicalSlotPreviewCard
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: modelData.key === "individual" ? 177 : 130
                                    color: "#FFFFFF"
                                    border.color: "#CFD9EA"
                                    radius: 10
                                    Label {
                                        x: 10; y: 6; width: parent.width - 20; height: 22
                                        text: canonicalSlotPreviewCard.modelData.label
                                        font.bold: true; color: "#284F8F"
                                    }
                                    Image {
                                        id: realSlotThumbnail
                                        x: 8; y: 29
                                        width: parent.width - 16; height: parent.height - 35
                                        source: window.slotPreviewCatalog[
                                            canonicalSlotPreviewCard.modelData.key
                                            + ((slotPriceMode.currentIndex === 2
                                                && canonicalSlotPreviewCard.modelData.key !== "blue")
                                                ? "-two" : "")
                                        ] || ""
                                        fillMode: Image.PreserveAspectFit
                                        asynchronous: true
                                        cache: false
                                        smooth: true
                                    }
                                    Label {
                                        anchors.centerIn: realSlotThumbnail
                                        visible: realSlotThumbnail.status === Image.Error ||
                                                 realSlotThumbnail.source.toString() === ""
                                        text: "Prévia não disponível"
                                        font.pixelSize: 11; color: "#64748B"
                                    }
                                    MouseArea {
                                        id: slotPaletteMouse
                                        anchors.fill: parent
                                        cursorShape: Qt.OpenHandCursor
                                        preventStealing: true
                                        property real originX: 0
                                        property real originY: 0
                                        property bool dragging: false
                                        onPressed: {
                                            originX = mouse.x; originY = mouse.y
                                            dragging = false
                                        }
                                        onPositionChanged: {
                                            if (!pressed) return
                                            var distance = Math.hypot(mouse.x-originX, mouse.y-originY)
                                            if (!dragging && distance >= 7)
                                                dragging = true
                                            if (dragging) {
                                                window.slotDragActive = true
                                                window.slotDragKey = canonicalSlotPreviewCard.modelData.key
                                                var point = mapToItem(window.contentItem, mouse.x, mouse.y)
                                                window.slotDragX = point.x
                                                window.slotDragY = point.y
                                            }
                                        }
                                        onReleased: {
                                            var key = canonicalSlotPreviewCard.modelData.key
                                            if (dragging) {
                                                window.placeSlotAt(key, slotPaletteMouse, mouse.x, mouse.y)
                                            } else if (key === "blue") {
                                                window.createBlueSlot()
                                            } else if (key === "individual") {
                                                window.createIndividualSlot()
                                            } else {
                                                window.createMultiSlot(canonicalSlotPreviewCard.modelData.count)
                                            }
                                            dragging = false; window.slotDragActive = false
                                        }
                                        onCanceled: {
                                            dragging = false; window.slotDragActive = false
                                        }
                                    }
                                }
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
                            Label { visible: studioSection === 1; text: "Cores e Estilos"; color: "#284F8F"; font.bold: true }
                            ComboBox {
                                id: slotThemeChoice
                                visible: studioSection === 1; Layout.fillWidth: true
                                model: ["Azul SR", "Verde Terça Verde", "Marrom Quarta Café", "Vinho Quinta Filé", "Vermelho Churrasco", "Personalizada"]
                            }
                            TextField {
                                id: slotCustomColor
                                visible: studioSection === 1 && slotThemeChoice.currentIndex === 5
                                Layout.fillWidth: true; text: "#075D08"; placeholderText: "#RRGGBB"
                            }
                            RowLayout {
                                visible: studioSection === 1; Layout.fillWidth: true
                                Button {
                                    Layout.fillWidth: true; text: "Selecionado"
                                    enabled: selectedSlotId !== ""
                                    onClicked: sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_slot_theme", "slot_id":selectedSlotId,
                                        "theme":slotThemeChoice.currentIndex === 5 ? slotCustomColor.text :
                                            (["azul", "terca-verde", "quarta-cafe", "quinta-file", "churrasco"][slotThemeChoice.currentIndex])
                                    }))
                                }
                                Button {
                                    Layout.fillWidth: true; text: "Página inteira"
                                    onClicked: sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_slot_theme", "entire_page":true,
                                        "theme":slotThemeChoice.currentIndex === 5 ? slotCustomColor.text :
                                            (["azul", "terca-verde", "quarta-cafe", "quinta-file", "churrasco"][slotThemeChoice.currentIndex])
                                    }))
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
                            Layout.fillHeight: true; Layout.fillWidth: true
                            visible: studioSection === 4 || studioSection === 5; spacing: 11
                            Button { Layout.fillWidth: true; visible: studioSection === 4; text: "+ Texto"; onClicked: sceneBridge.dispatch('{"name":"add_text"}') }
                            Button { Layout.fillWidth: true; visible: studioSection === 5; text: "+ Forma"; onClicked: sceneBridge.dispatch('{"name":"add_rect"}') }
                            Item { Layout.fillHeight: true }
                        }
                        ScrollView {
                            Layout.fillHeight: true; Layout.fillWidth: true
                            visible: studioSection === 6; clip: true
                            ColumnLayout {
                                width: 235; spacing: 12
                                Label { text: "Campanha"; color: "#284F8F"; font.bold: true }
                                ComboBox {
                                    id: campaignCampaignChoice
                                    Layout.fillWidth: true
                                    model: ["Terça Verde", "Quarta Café com Pão", "Quinta Filé", "Churrasco / Açougue"]
                                }
                                Label {
                                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                                    color: "#64748B"
                                    text: "Escolha uma miniatura. O fundo ocupa toda a página e o selo correspondente é colocado automaticamente. Sem importar arquivos."
                                }
                                Label { text: "Fundos Promocionais"; color: "#284F8F"; font.bold: true }
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2
                                    rowSpacing: 8; columnSpacing: 7
                                    Repeater {
                                        model: window.campaignArtworkList("background")
                                        delegate: Rectangle {
                                            required property var modelData
                                            required property int index
                                            Layout.preferredWidth: 109
                                            Layout.preferredHeight: 158
                                            color: "#F8FAFC"
                                            radius: 7; border.width: 1
                                            border.color: page && page.metadata && page.metadata.campaign_background_asset === modelData.id
                                                ? "#1673C5" : "#DDE5F0"
                                            Image {
                                                anchors.left: parent.left; anchors.right: parent.right
                                                anchors.top: parent.top; anchors.margins: 5
                                                height: 125; asynchronous: true
                                                source: modelData.preview_url || ""
                                                fillMode: Image.PreserveAspectCrop
                                                sourceSize.width: 148
                                            }
                                            Label {
                                                anchors.bottom: parent.bottom
                                                anchors.left: parent.left; anchors.right: parent.right
                                                height: 20; horizontalAlignment: Text.AlignHCenter
                                                font.pixelSize: 10; elide: Text.ElideRight
                                                text: modelData.name || "Fundo"
                                            }
                                            MouseArea {
                                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                onClicked: window.applyInstalledCampaignArt("background", index)
                                            }
                                        }
                                    }
                                }
                                Label { text: "Logos e Selos Promocionais"; color: "#284F8F"; font.bold: true }
                                Label {
                                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                                    color: "#64748B"
                                    text: "O logo padrão acompanha o fundo; toque em outra miniatura para trocar somente o logo."
                                }
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2
                                    rowSpacing: 8; columnSpacing: 7
                                    Repeater {
                                        model: window.campaignArtworkList("seal")
                                        delegate: Rectangle {
                                            required property var modelData
                                            required property int index
                                            Layout.preferredWidth: 109
                                            Layout.preferredHeight: 112
                                            color: "#F8FAFC"; radius: 7; border.width: 1
                                            border.color: page && page.metadata && page.metadata.campaign_seal_asset === modelData.id
                                                ? "#1673C5" : "#DDE5F0"
                                            Image {
                                                anchors.left: parent.left; anchors.right: parent.right
                                                anchors.top: parent.top; anchors.margins: 4
                                                height: 85; asynchronous: true
                                                source: modelData.preview_url || ""
                                                fillMode: Image.PreserveAspectFit
                                                sourceSize.width: 148
                                            }
                                            Label {
                                                anchors.bottom: parent.bottom
                                                anchors.left: parent.left; anchors.right: parent.right
                                                height: 20; horizontalAlignment: Text.AlignHCenter
                                                font.pixelSize: 10; elide: Text.ElideRight
                                                text: modelData.name || "Selo"
                                            }
                                            MouseArea {
                                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                onClicked: window.applyInstalledCampaignArt("seal", index)
                                            }
                                        }
                                    }
                                }
                                Rectangle { Layout.fillWidth: true; height: 1; color: "#E5EAF4" }
                                Label { text: "Data da Promoção"; color: "#284F8F"; font.bold: true }
                                ComboBox {
                                    id: campaignDateMode
                                    Layout.fillWidth: true
                                    model: ["Automática · planilha", "Manual"]
                                }
                                Label {
                                    text: "Uma data única e válida na planilha é necessária para preenchimento automático."
                                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: "#64748B"
                                }
                                TextField {
                                    id: campaignManualDate
                                    Layout.fillWidth: true; placeholderText: "DD/MM/AAAA"
                                    visible: campaignDateMode.currentIndex === 1
                                    inputMask: "99/99/9999"
                                }
                                Button {
                                    Layout.fillWidth: true; text: "Aplicar data"
                                    onClicked: sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_campaign_date",
                                        "mode":campaignDateMode.currentIndex === 0 ? "auto" : "manual",
                                        "value":campaignDateMode.currentIndex === 0 ? null : campaignManualDate.text
                                    }))
                                }
                                Label {
                                    text: "Exibida: " + String((page && page.metadata && page.metadata.campaign_date_display) || "não definida")
                                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: "#425072"
                                }
                                CheckBox { text: "Mostrar grade"; checked: showGrid; onToggled: showGrid = checked }
                                CheckBox { text: "Mostrar réguas"; checked: showRulers; onToggled: showRulers = checked }
                            }
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
                                MenuItem { text: "Duplicar Smart Slot  ·  Ctrl+D"; enabled: selectedSlotId !== ""; onTriggered: duplicateSelectedSmartSlot() }
                                MenuItem { text: "Excluir Slot"; enabled: selectedSlotId !== ""; onTriggered: sceneBridge.dispatch(JSON.stringify({"name":"delete_smart_slot","slot_id":selectedSlotId})) }
                                MenuItem { text: "Não-produto"; enabled: selectedSlotId !== ""; onTriggered: sceneBridge.dispatch(JSON.stringify({"name":"mark_smart_slot_non_product","slot_id":selectedSlotId})) }
                                MenuItem { text: "Fundo automático"; checkable: true; checked: autoRemoveProductBackground; onTriggered: autoRemoveProductBackground = checked }
                            }
                        }
                        ToolButton { text: "T"; ToolTip.text: "Texto"; ToolTip.visible: hovered; onClicked: sceneBridge.dispatch('{"name":"add_text"}') }
                        ToolButton { text: "▧"; ToolTip.text: "Imagens dos produtos"; ToolTip.visible: hovered; onClicked: studioSection = 0 }
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
                                        text: modelData.style.single_line
                                              ? String(modelData.text || "").replace(/\\s+/g, " ").trim()
                                              : (modelData.text || "")
                                        color: modelData.style.color || "#111827"
                                        font.family: modelData.style.font_family || "Segoe UI"
                                        font.pixelSize: Math.max(4, Number(modelData.style.font_size || 20) * (String(modelData.style.font_size_unit || "pt") === "pt" ? 1.333333 : 1) * zoom)
                                        font.bold: Number(modelData.style.font_weight || 400) >= 700
                                        font.italic: !!modelData.style.italic
                                        font.letterSpacing: Number(modelData.style.letter_spacing || 0) * zoom
                                        horizontalAlignment: modelData.style.align === "left" ? Text.AlignLeft : modelData.style.align === "right" ? Text.AlignRight : Text.AlignHCenter
                                        verticalAlignment: modelData.style.v_align === "top" ? Text.AlignTop : modelData.style.v_align === "bottom" ? Text.AlignBottom : Text.AlignVCenter
                                        wrapMode: (modelData.style.single_line || modelData.style.nowrap) ? Text.NoWrap : Text.WordWrap
                                        maximumLineCount: modelData.style.single_line ? 1 : 2147483647
                                        // HorizontalFit shrinks text horizontally, never stacks words.
                                        fontSizeMode: modelData.style.single_line ? Text.HorizontalFit : (fitTextInside ? Text.Fit : Text.FixedSize)
                                        // Respect the existing slot typography contract at every zoom.
                                        // The PNG/PDF renderer already uses min_font_size.
                                        minimumPixelSize: Math.max(1, Number(modelData.style.min_font_size || 4) * zoom)
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
                                        mipmap: !(modelData.metadata && modelData.metadata.campaign_art)
                                        sourceSize.width: modelData.metadata && modelData.metadata.campaign_art
                                            ? Math.min(4096, Math.max(1200, Number(modelData.transform.width || 1080) * 1.5)) : -1
                                        sourceSize.height: modelData.metadata && modelData.metadata.campaign_art
                                            ? Math.min(4096, Math.max(1400, Number(modelData.transform.height || 1350) * 1.5)) : -1
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
                                model: slots().filter(function(slot) {
                                    return !slot.metadata || !slot.metadata.multi_parent_id ||
                                           Number(slot.metadata.multi_index || 0) === 0
                                })
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
                                        // Continuous per-cell badges obscured source names
                                        // on every Multi when edit mode was enabled.
                                        visible: isSelectedSlot || isHoveredSlot || isDropTarget
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
                                            window.inspectorProduct = null
                                            Qt.callLater(window.refreshPropertyFields)
                                            if (!smartSlotEditMode)
                                                return
                                            var point = mapToItem(sheet, mouse.x, mouse.y)
                                            startGlobalX = point.x / zoom
                                            startGlobalY = point.y / zoom
                                            startBounds = {"x":slotOverlay.bounds.x,"y":slotOverlay.bounds.y,"width":slotOverlay.bounds.width,"height":slotOverlay.bounds.height}
                                            slotOverlay.beginPreview(startBounds, "move")
                                        }
                                        onClicked: {
                                            selectedSlotId = slotOverlay.modelData.id
                                            window.inspectorProduct = null
                                            Qt.callLater(window.refreshPropertyFields)
                                        }
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
                        GroupBox {
                            title: "Produto selecionado"
                            visible: !!window.propertyProduct()
                            Layout.fillWidth: true
                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 8
                                Label { text: "Nome do produto"; color: "#53617A"; font.pixelSize: 10 }
                                TextField { id: inspectorProductName; Layout.fillWidth: true; placeholderText: "Nome completo"; font.pixelSize: 12 }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Label { text: "Preço (R$)"; font.pixelSize: 10; color: "#53617A" }
                                        TextField { id: inspectorPrice; Layout.fillWidth: true; placeholderText: "0,00" }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Label { text: "Clube SR / App"; font.pixelSize: 10; color: "#53617A" }
                                        TextField { id: inspectorAppPrice; Layout.fillWidth: true; placeholderText: "0,00" }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Unidade"; color: "#53617A" }
                                    TextField { id: inspectorUnit; Layout.fillWidth: true; placeholderText: "UN ou KG" }
                                }
                                Button {
                                    text: "Salvar dados do produto"
                                    Layout.fillWidth: true
                                    highlighted: true
                                    onClicked: window.saveProductProperties()
                                }
                            }
                        }
                        GroupBox {
                            title: "Smart Slot · Formatação"
                            Layout.fillWidth: true
                            visible: selectedSlotId !== ""
                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 9
                                Button {
                                    text: "Duplicar Smart Slot  ·  Ctrl + D"
                                    Layout.fillWidth: true
                                    onClicked: window.duplicateSelectedSmartSlot()
                                }
                                Label { text: "Alinhamento do nome"; color: "#53617A"; font.pixelSize: 10 }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Repeater {
                                        model: [
                                            {"label":"◧", "alignment":"left"},
                                            {"label":"☷", "alignment":"center"},
                                            {"label":"◨", "alignment":"right"}
                                        ]
                                        delegate: Button {
                                            required property var modelData
                                            Layout.fillWidth: true
                                            text: modelData.label
                                            onClicked: sceneBridge.dispatch(JSON.stringify({
                                                "name":"set_slot_typography",
                                                "slot_id":selectedSlotId,
                                                "role":"name", "align":modelData.alignment
                                            }))
                                        }
                                    }
                                }
                                Label { text: "Tipografia"; color: "#12295A"; font.bold: true }
                                RowLayout {
                                    Layout.fillWidth: true
                                    ComboBox {
                                        id: inspectorFont
                                        Layout.fillWidth: true
                                        model: ["Impact", "Arial", "Poppins", "Segoe UI", "Anton"]
                                    }
                                    SpinBox {
                                        id: inspectorFontSize
                                        from: 8; to: 90; value: 22
                                        editable: true
                                        Layout.preferredWidth: 83
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Cor"; color: "#53617A" }
                                    TextField {
                                        id: inspectorFontColor
                                        Layout.fillWidth: true
                                        text: "#B32D18"
                                        placeholderText: "#RRGGBB"
                                    }
                                }
                                Button {
                                    text: "Aplicar tipografia"
                                    Layout.fillWidth: true
                                    onClicked: sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_slot_typography",
                                        "slot_id":selectedSlotId,
                                        "role":"name",
                                        "font_family":inspectorFont.currentText,
                                        "font_size":inspectorFontSize.value,
                                        "color":inspectorFontColor.text,
                                        "font_weight":700
                                    }))
                                }
                                Label { text: "Estilo do preço"; font.bold: true; color: "#12295A" }
                                ComboBox {
                                    id: inspectorPriceStyle
                                    Layout.fillWidth: true
                                    model: ["Automático", "1 preço", "2 preços"]
                                    onActivated: sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_item_price_mode",
                                        "slot_id":selectedSlotId,
                                        "mode":["auto","one","two"][currentIndex]
                                    }))
                                }
                                Label { text: "Cores da campanha"; font.bold: true; color: "#12295A" }
                                ComboBox {
                                    id: inspectorTheme
                                    Layout.fillWidth: true
                                    model: ["Azul SR", "Verde Terça", "Marrom Café", "Vinho Filé", "Vermelho Churrasco"]
                                    onActivated: sceneBridge.dispatch(JSON.stringify({
                                        "name":"set_slot_theme",
                                        "slot_id":selectedSlotId,
                                        "theme":["azul","terca-verde","quarta-cafe","quinta-file","churrasco"][currentIndex]
                                    }))
                                }
                            }
                        }
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
        id: slotDragGhost
        visible: window.slotDragActive
        x: window.slotDragX + 12
        y: window.slotDragY + 12
        width: 192
        height: 46
        z: 1000020
        radius: 9
        color: "#F8FAFF"
        border.width: 2
        border.color: "#2166EF"
        opacity: .96
        Label {
            anchors.centerIn: parent
            text: "Soltar · " + (window.slotDragKey === "blue" ? "Slot Único" :
                  window.slotDragKey === "individual" ? "Individual" :
                  window.slotDragKey === "multi5" ? "Multi 5" : "Multi 6")
            color: "#164FAF"
            font.bold: true
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
