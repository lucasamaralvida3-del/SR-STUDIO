import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Rectangle {
    id: panel
    width: 332
    height: Math.min(690, parent ? parent.height - 86 : 690)
    anchors.right: parent ? parent.right : undefined
    anchors.top: parent ? parent.top : undefined
    anchors.rightMargin: 352
    anchors.topMargin: 58
    z: 899500
    radius: 9
    color: "#FFFFFFF8"
    border.width: 1
    border.color: "#CBD5E1"

    property var scene: ({})
    property var context: ({})
    property var pageState: ({})
    property var usability: ({})
    property var currentPage: null
    property var currentNode: null
    property var currentSlot: null
    property bool syncing: false
    property string pendingImageSource: ""
    property string fillPlanToken: ""
    property int fillPlanCount: 0

    function activePage() {
        if (!scene.pages || !scene.pages.length)
            return null
        for (var i = 0; i < scene.pages.length; ++i)
            if (scene.pages[i].id === scene.active_page_id)
                return scene.pages[i]
        return scene.pages[0]
    }

    function nodeById(id) {
        if (!currentPage || !currentPage.nodes || !id)
            return null
        return currentPage.nodes[String(id)] || null
    }

    function slotById(id) {
        if (!currentPage || !currentPage.slots || !id)
            return null
        return currentPage.slots[String(id)] || null
    }

    function send(command) {
        try {
            return JSON.parse(sceneBridge.dispatch(JSON.stringify(command)))
        } catch (error) {
            return {"ok": false, "message": String(error), "command_payload": ({})}
        }
    }

    function snapshotValue(key, fallbackValue) {
        if (!currentSlot || !currentSlot.metadata)
            return fallbackValue
        var snapshot = currentSlot.metadata.product_snapshot || ({})
        var value = snapshot[key]
        return value === undefined || value === null ? fallbackValue : value
    }

    function styleValue(key, fallbackValue) {
        if (!currentNode || !currentNode.style)
            return fallbackValue
        var value = currentNode.style[key]
        return value === undefined || value === null ? fallbackValue : value
    }

    function refresh() {
        syncing = true
        try {
            scene = JSON.parse(sceneBridge.sceneJson)
            var professional = scene.editor && scene.editor.professional ? scene.editor.professional : ({})
            context = professional.inspector || ({})
            pageState = professional.page || ({})
            usability = professional.usability || ({})
            currentPage = activePage()
            currentNode = nodeById(context.target_id || "")
            currentSlot = slotById(context.slot_id || "")

            if (context.target_type === "page") {
                pageName.text = currentPage ? String(currentPage.name || "") : ""
            } else if (context.target_type === "text" && currentNode) {
                textContent.text = String(currentNode.text || "")
                fontFamily.text = String(styleValue("font_family", ""))
                fontSize.value = Number(styleValue("font_size", 24))
                textColor.text = String(styleValue("color", "#111827"))
            } else if (context.target_type === "product_card") {
                productName.text = String(snapshotValue("display_name", snapshotValue("name", "")))
                productPrice.text = String(snapshotValue("price", ""))
                productUnit.text = String(snapshotValue("unit", ""))
                productLimit.text = String(snapshotValue("limit", snapshotValue("cpf_limit", "")))
                productAppPrice.text = String(snapshotValue("app_price", ""))
                pendingImageSource = ""
            } else if (context.target_type === "price_block") {
                blockPrice.text = String(snapshotValue("price", ""))
                blockUnit.text = String(snapshotValue("unit", ""))
            }
        } finally {
            syncing = false
        }
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { panel.refresh() }
    }
    Component.onCompleted: refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 9
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            Label { text: "Studio de Encartes PRO"; font.bold: true; font.pixelSize: 15; color: "#0F172A" }
            Item { Layout.fillWidth: true }
            Rectangle {
                radius: 8
                implicitWidth: gateLabel.implicitWidth + 12
                implicitHeight: 22
                color: Number(usability.blockers || 0) === 0 ? "#DCFCE7" : "#FEE2E2"
                Label {
                    id: gateLabel
                    anchors.centerIn: parent
                    text: Number(usability.blockers || 0) === 0 ? "estrutura OK" : String(usability.blockers || 0) + " bloqueio(s)"
                    font.pixelSize: 9
                    font.bold: true
                    color: Number(usability.blockers || 0) === 0 ? "#166534" : "#991B1B"
                }
            }
        }

        Label {
            Layout.fillWidth: true
            text: String(context.title || "Página")
            color: "#475569"
            font.pixelSize: 11
            elide: Text.ElideRight
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#E2E8F0" }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                width: Math.max(290, parent ? parent.width - 12 : 290)
                spacing: 7

                ColumnLayout {
                    visible: context.target_type === "page"
                    Layout.fillWidth: true
                    Label { text: "Página"; font.bold: true; color: "#334155" }
                    TextField { id: pageName; Layout.fillWidth: true; placeholderText: "Nome da página" }
                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            text: "Renomear"
                            Layout.fillWidth: true
                            onClicked: if (currentPage) send({"name":"rename_page", "page_id":currentPage.id, "name_value":pageName.text})
                        }
                        Button {
                            text: "Duplicar"
                            Layout.fillWidth: true
                            onClicked: if (currentPage) send({"name":"duplicate_page", "page_id":currentPage.id})
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            text: "←"
                            enabled: !!pageState.can_move_previous
                            Layout.fillWidth: true
                            onClicked: send({"name":"reorder_page", "page_id":currentPage.id, "mode":"previous"})
                        }
                        Button {
                            text: "→"
                            enabled: !!pageState.can_move_next
                            Layout.fillWidth: true
                            onClicked: send({"name":"reorder_page", "page_id":currentPage.id, "mode":"next"})
                        }
                        Button {
                            text: "Excluir"
                            enabled: !!pageState.can_delete
                            Layout.fillWidth: true
                            onClicked: if (currentPage) send({"name":"delete_page", "page_id":currentPage.id})
                        }
                    }
                    Label {
                        text: "Página " + (Number(pageState.index || 0) + 1) + " de " + Number(pageState.count || 1)
                        color: "#64748B"
                        font.pixelSize: 9
                    }
                }

                ColumnLayout {
                    visible: context.target_type === "text"
                    Layout.fillWidth: true
                    Label { text: "Texto"; font.bold: true; color: "#334155" }
                    TextArea {
                        id: textContent
                        Layout.fillWidth: true
                        Layout.preferredHeight: 72
                        wrapMode: TextEdit.Wrap
                    }
                    TextField { id: fontFamily; Layout.fillWidth: true; placeholderText: "Fonte" }
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: "Tamanho"; color: "#475569" }
                        SpinBox { id: fontSize; from: 1; to: 500; value: 24; editable: true; Layout.fillWidth: true }
                        TextField { id: textColor; text: "#111827"; Layout.preferredWidth: 92; placeholderText: "#RRGGBB" }
                    }
                    Button {
                        text: "Aplicar texto e estilo"
                        Layout.fillWidth: true
                        onClicked: {
                            if (!currentNode) return
                            send({"name":"edit_text", "node_id":currentNode.id, "text":textContent.text})
                            send({"name":"edit_text_style", "node_id":currentNode.id, "font_family":fontFamily.text, "font_size":fontSize.value, "color":textColor.text})
                        }
                    }
                }

                ColumnLayout {
                    visible: context.target_type === "image"
                    Layout.fillWidth: true
                    Label { text: "Imagem"; font.bold: true; color: "#334155" }
                    Label { text: "A substituição preserva crop, foco, zoom e tamanho por padrão."; wrapMode: Text.WordWrap; Layout.fillWidth: true; color: "#64748B"; font.pixelSize: 9 }
                    Button { text: "Substituir imagem…"; Layout.fillWidth: true; onClicked: replaceImageDialog.open() }
                    Button {
                        text: "Substituir e resetar enquadramento…"
                        Layout.fillWidth: true
                        onClicked: replaceImageResetDialog.open()
                    }
                }

                ColumnLayout {
                    visible: context.target_type === "product_card"
                    Layout.fillWidth: true
                    Label { text: "ProductCard"; font.bold: true; color: "#334155" }
                    TextField { id: productName; Layout.fillWidth: true; placeholderText: "Nome do produto" }
                    RowLayout {
                        Layout.fillWidth: true
                        TextField { id: productPrice; Layout.fillWidth: true; placeholderText: "Preço 25,77" }
                        TextField { id: productUnit; Layout.preferredWidth: 72; placeholderText: "KG" }
                    }
                    TextField { id: productLimit; Layout.fillWidth: true; placeholderText: "Limite ex.: 6UN" }
                    TextField { id: productAppPrice; Layout.fillWidth: true; placeholderText: "Preço App (opcional)" }
                    RowLayout {
                        Layout.fillWidth: true
                        Button { text: "Imagem…"; Layout.fillWidth: true; onClicked: productImageDialog.open() }
                        Label { text: pendingImageSource ? "selecionada" : "manter atual"; color: "#64748B"; font.pixelSize: 9 }
                    }
                    Button {
                        text: "Aplicar ProductCard"
                        Layout.fillWidth: true
                        enabled: !!context.slot_id
                        onClicked: {
                            var command = {"name":"edit_product_card", "slot_id":String(context.slot_id || ""), "name":productName.text, "price":productPrice.text, "unit":productUnit.text, "limit":productLimit.text}
                            if (productAppPrice.text.length) command.app_price = productAppPrice.text
                            if (pendingImageSource.length) command.image_source = pendingImageSource
                            send(command)
                            pendingImageSource = ""
                        }
                    }
                }

                ColumnLayout {
                    visible: context.target_type === "price_block"
                    Layout.fillWidth: true
                    Label { text: "PriceBlock"; font.bold: true; color: "#334155" }
                    RowLayout {
                        Layout.fillWidth: true
                        TextField { id: blockPrice; Layout.fillWidth: true; placeholderText: "Preço" }
                        TextField { id: blockUnit; Layout.preferredWidth: 76; placeholderText: "KG" }
                    }
                    Button {
                        text: "Aplicar preço"
                        Layout.fillWidth: true
                        onClicked: send({"name":"edit_price_block", "block_id":String(context.target_id || ""), "price":blockPrice.text, "unit":blockUnit.text})
                    }
                }

                ColumnLayout {
                    visible: context.target_type === "multi"
                    Layout.fillWidth: true
                    Label { text: "Seleção múltipla"; font.bold: true; color: "#334155" }
                    RowLayout {
                        Layout.fillWidth: true
                        Button { text: "Esquerda"; Layout.fillWidth: true; onClicked: send({"name":"align", "mode":"left"}) }
                        Button { text: "Centro"; Layout.fillWidth: true; onClicked: send({"name":"align", "mode":"center"}) }
                        Button { text: "Direita"; Layout.fillWidth: true; onClicked: send({"name":"align", "mode":"right"}) }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Button { text: "Distribuir H"; Layout.fillWidth: true; onClicked: send({"name":"distribute", "axis":"horizontal"}) }
                        Button { text: "Distribuir V"; Layout.fillWidth: true; onClicked: send({"name":"distribute", "axis":"vertical"}) }
                    }
                }

                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#E2E8F0" }
                Label { text: "Automação do encarte"; font.bold: true; color: "#334155" }
                Button {
                    text: "Preparar preenchimento dos Smart Slots"
                    Layout.fillWidth: true
                    onClicked: {
                        var response = send({"name":"plan_slot_fill", "min_confidence":0.72})
                        var payload = response.command_payload || ({})
                        fillPlanToken = String(payload.plan_token || "")
                        fillPlanCount = payload.assignments ? payload.assignments.length : 0
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: fillPlanToken ? fillPlanCount + " slot(s) prontos para revisão" : "Nenhum plano preparado"; color: "#64748B"; font.pixelSize: 9; Layout.fillWidth: true }
                    Button {
                        text: "Aplicar"
                        enabled: fillPlanToken.length > 0 && fillPlanCount > 0
                        onClicked: {
                            var response = send({"name":"apply_slot_fill", "plan_token":fillPlanToken})
                            if (response.ok) { fillPlanToken = ""; fillPlanCount = 0 }
                        }
                    }
                }

                Button {
                    text: "Verificar / reparar IDs antigos"
                    Layout.fillWidth: true
                    visible: Number(usability.blockers || 0) > 0
                    onClicked: send({"name":"repair_legacy_identities"})
                }

                Label {
                    Layout.fillWidth: true
                    text: "Modo PRO é opt-in. Golden Masters e Production Gate oficial permanecem inalterados."
                    wrapMode: Text.WordWrap
                    color: "#64748B"
                    font.pixelSize: 9
                }
            }
        }
    }

    FileDialog {
        id: replaceImageDialog
        title: "Substituir imagem preservando enquadramento"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp)", "Todos os arquivos (*)"]
        onAccepted: if (currentNode) send({"name":"replace_image", "node_id":currentNode.id, "source":selectedFile.toString().replace(/^file:\/\/\//, "")})
    }
    FileDialog {
        id: replaceImageResetDialog
        title: "Substituir imagem e resetar enquadramento"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp)", "Todos os arquivos (*)"]
        onAccepted: if (currentNode) send({"name":"replace_image", "node_id":currentNode.id, "source":selectedFile.toString().replace(/^file:\/\/\//, ""), "reset_framing":true})
    }
    FileDialog {
        id: productImageDialog
        title: "Imagem do ProductCard"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Imagens (*.png *.jpg *.jpeg *.webp *.bmp)", "Todos os arquivos (*)"]
        onAccepted: pendingImageSource = selectedFile.toString().replace(/^file:\/\/\//, "")
    }
}
