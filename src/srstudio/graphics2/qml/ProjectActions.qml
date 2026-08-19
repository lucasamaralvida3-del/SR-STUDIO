import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window

Rectangle {
    id: panel
    width: Math.min(1230, parent ? parent.width - 340 : 1230)
    height: 42
    anchors.left: parent ? parent.left : undefined
    anchors.top: parent ? parent.top : undefined
    anchors.leftMargin: 324
    anchors.topMargin: 7
    z: 897000
    radius: 8
    color: "#FFFFFFF5"
    border.width: 1
    border.color: "#CBD5E1"

    property var scene: ({})
    property string activeManualSlotId: ""

    function refreshScene() {
        try {
            scene = JSON.parse(sceneBridge.sceneJson)
        } catch (error) {
            scene = ({})
        }
        var current = manualSlots()
        var found = false
        for (var i = 0; i < current.length; ++i)
            if (String(current[i].slot_id) === String(activeManualSlotId))
                found = true
        if (!found)
            activeManualSlotId = current.length ? String(current[0].slot_id) : ""
        Qt.callLater(syncRoleEditor)
    }

    function pageCount() {
        return scene.pages ? scene.pages.length : 0
    }

    function activePageIndex() {
        if (!scene.pages)
            return -1
        for (var i = 0; i < scene.pages.length; ++i)
            if (String(scene.pages[i].id) === String(scene.active_page_id || ""))
                return i
        return scene.pages.length ? 0 : -1
    }

    function itemSlotPresets() {
        return scene.editor && scene.editor.item_slot_presets ? scene.editor.item_slot_presets : []
    }

    function manualSlots() {
        var all = scene.editor && scene.editor.item_slots ? scene.editor.item_slots : []
        var result = []
        for (var i = 0; i < all.length; ++i)
            if (String(all[i].page_id || "") === String(scene.active_page_id || ""))
                result.push(all[i])
        return result
    }

    function activeManualSlot() {
        var all = manualSlots()
        for (var i = 0; i < all.length; ++i)
            if (String(all[i].slot_id) === String(activeManualSlotId))
                return all[i]
        return null
    }

    function selectedRoleData() {
        var slot = activeManualSlot()
        if (!slot || !slot.internal_roles)
            return null
        return slot.internal_roles[String(roleCombo.currentValue || "")]
    }

    function syncRoleEditor() {
        var role = selectedRoleData()
        if (!role) {
            roleX.text = ""
            roleY.text = ""
            roleW.text = ""
            roleH.text = ""
            return
        }
        roleX.text = Number(role.x).toFixed(2)
        roleY.text = Number(role.y).toFixed(2)
        roleW.text = Number(role.width).toFixed(2)
        roleH.text = Number(role.height).toFixed(2)
    }

    function addPreset(presetId) {
        var raw = sceneBridge.dispatch(JSON.stringify({"name":"add_item_slot", "preset_id": presetId}))
        try {
            var result = JSON.parse(raw)
            if (result.ok && result.payload && result.payload.slot_id)
                activeManualSlotId = String(result.payload.slot_id)
        } catch (error) {}
        presetMenu.close()
        itemSlotPopup.open()
    }

    function selectActiveSlot() {
        if (!activeManualSlotId)
            return
        sceneBridge.dispatch(JSON.stringify({"name":"select_item_slot", "slot_id": activeManualSlotId}))
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { panel.refreshScene() }
    }

    Connections {
        target: panel.Window.window
        function onClosing(close) {
            sceneBridge.flushAutosave()
            if (String(sceneBridge.status || "").indexOf("Falha no autosave final:") === 0)
                close.accepted = false
        }
    }

    Component.onCompleted: refreshScene()

    Shortcut { sequence: StandardKey.Save; onActivated: saveDialog.open() }
    Shortcut { sequence: StandardKey.Copy; onActivated: sceneBridge.dispatch('{"name":"copy"}') }
    Shortcut { sequence: StandardKey.Paste; onActivated: sceneBridge.dispatch('{"name":"paste"}') }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 5

        Label { text: "Página"; color: "#475569"; font.bold: true; font.pixelSize: 10 }
        ComboBox {
            id: pageCombo
            Layout.preferredWidth: 118
            enabled: !sceneBridge.busy && panel.pageCount() > 0
            model: panel.scene.pages || []
            textRole: "name"
            currentIndex: panel.activePageIndex()
            ToolTip.text: "Navegar entre páginas do encarte"
            ToolTip.visible: hovered
            onActivated: {
                if (currentIndex >= 0 && panel.scene.pages && currentIndex < panel.scene.pages.length)
                    sceneBridge.dispatch(JSON.stringify({"name": "select_page", "page_id": panel.scene.pages[currentIndex].id}))
            }
        }
        ToolButton { text: "+"; enabled: !sceneBridge.busy; ToolTip.text: "Adicionar página"; ToolTip.visible: hovered; onClicked: sceneBridge.dispatch('{"name":"add_page"}') }
        ToolButton { text: "⧉"; enabled: !sceneBridge.busy && panel.pageCount() > 0; ToolTip.text: "Duplicar página"; ToolTip.visible: hovered; onClicked: sceneBridge.dispatch('{"name":"duplicate_page"}') }
        ToolButton { text: "←"; enabled: !sceneBridge.busy && panel.activePageIndex() > 0; onClicked: sceneBridge.dispatch(JSON.stringify({"name":"reorder_page", "page_id": panel.scene.active_page_id || "", "mode":"previous"})) }
        ToolButton { text: "→"; enabled: !sceneBridge.busy && panel.activePageIndex() >= 0 && panel.activePageIndex() < panel.pageCount() - 1; onClicked: sceneBridge.dispatch(JSON.stringify({"name":"reorder_page", "page_id": panel.scene.active_page_id || "", "mode":"next"})) }
        ToolButton { text: "×"; enabled: !sceneBridge.busy && panel.pageCount() > 1; onClicked: sceneBridge.dispatch(JSON.stringify({"name":"delete_page", "page_id": panel.scene.active_page_id || ""})) }

        ToolSeparator {}
        ToolButton {
            id: addItemSlotButton
            text: "+ SLOT DE ITEM"
            enabled: !sceneBridge.busy
            font.bold: true
            ToolTip.text: "Adicionar componente de produto manual · não depende de detecção automática"
            ToolTip.visible: hovered
            onClicked: presetMenu.open()
        }
        ToolButton {
            text: "Editar Slot"
            enabled: panel.manualSlots().length > 0 && !sceneBridge.busy
            onClicked: itemSlotPopup.open()
        }

        ToolSeparator {}
        ToolButton { text: "Copiar"; enabled: !sceneBridge.busy; onClicked: sceneBridge.dispatch('{"name":"copy"}') }
        ToolButton { text: "Colar"; enabled: !sceneBridge.busy; onClicked: sceneBridge.dispatch('{"name":"paste"}') }
        ToolButton { text: "💾 Salvar"; enabled: !sceneBridge.busy; onClicked: saveDialog.open() }
        ToolButton { text: "↺"; enabled: !sceneBridge.busy; ToolTip.text: "Recuperar autosave"; ToolTip.visible: hovered; onClicked: sceneBridge.recoverLatest() }
        ToolButton { text: "PDF"; enabled: !sceneBridge.busy; onClicked: pdfDialog.open() }
        ToolButton { text: "PNG"; enabled: !sceneBridge.busy; onClicked: pngDialog.open() }
        Item { Layout.fillWidth: true }
        BusyIndicator { running: sceneBridge.busy; visible: running; implicitWidth: 24; implicitHeight: 24 }
    }

    Menu {
        id: presetMenu
        y: panel.height + 3
        Repeater {
            model: panel.itemSlotPresets()
            delegate: MenuItem {
                required property var modelData
                text: String(modelData.name || modelData.id || "Preset")
                onTriggered: panel.addPreset(String(modelData.id || "simples"))
            }
        }
    }

    Popup {
        id: itemSlotPopup
        parent: Overlay.overlay
        modal: false
        focus: true
        width: 470
        height: 520
        x: Math.max(16, (parent ? parent.width : 900) - width - 28)
        y: 62
        padding: 14
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: "#FFFFFF"; border.color: "#CBD5E1"; radius: 10 }

        ColumnLayout {
            anchors.fill: parent
            spacing: 9

            RowLayout {
                Layout.fillWidth: true
                Label { text: "EDITAR SLOT DE ITEM"; font.bold: true; font.pixelSize: 16; color: "#111827" }
                Item { Layout.fillWidth: true }
                ToolButton { text: "×"; onClicked: itemSlotPopup.close() }
            }
            Label {
                Layout.fillWidth: true
                text: "Ajuste IMAGE, NAME, PRICE e UNIT separadamente. Alterar uma área não deforma as demais."
                wrapMode: Text.WordWrap
                color: "#64748B"
                font.pixelSize: 10
            }

            Label { text: "Slot atual"; color: "#475569"; font.bold: true; font.pixelSize: 10 }
            ComboBox {
                id: itemSlotCombo
                Layout.fillWidth: true
                model: panel.manualSlots()
                textRole: "name"
                onActivated: {
                    if (currentIndex >= 0 && currentIndex < model.length) {
                        panel.activeManualSlotId = String(model[currentIndex].slot_id)
                        panel.selectActiveSlot()
                        panel.syncRoleEditor()
                    }
                }
                Component.onCompleted: if (count > 0 && currentIndex >= 0) panel.activeManualSlotId = String(model[currentIndex].slot_id)
            }

            RowLayout {
                Layout.fillWidth: true
                Button { text: "Selecionar"; enabled: panel.activeManualSlotId !== ""; onClicked: panel.selectActiveSlot() }
                Button {
                    text: "Duplicar vazio"
                    enabled: panel.activeManualSlotId !== ""
                    onClicked: {
                        var raw = sceneBridge.dispatch(JSON.stringify({"name":"duplicate_item_slot", "slot_id": panel.activeManualSlotId}))
                        try {
                            var result = JSON.parse(raw)
                            if (result.ok && result.payload && result.payload.slot_id)
                                panel.activeManualSlotId = String(result.payload.slot_id)
                        } catch (error) {}
                    }
                }
                Button {
                    text: "Excluir"
                    enabled: panel.activeManualSlotId !== ""
                    onClicked: {
                        panel.selectActiveSlot()
                        sceneBridge.dispatch('{"name":"delete"}')
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: "#E2E8F0" }
            Label { text: "Área interna"; color: "#475569"; font.bold: true; font.pixelSize: 10 }
            ComboBox {
                id: roleCombo
                Layout.fillWidth: true
                model: [
                    {"label":"IMAGE AREA", "value":"image"},
                    {"label":"NAME AREA", "value":"name"},
                    {"label":"PRICE AREA", "value":"price"},
                    {"label":"UNIT AREA", "value":"unit"}
                ]
                textRole: "label"
                valueRole: "value"
                onActivated: panel.syncRoleEditor()
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 4
                columnSpacing: 6
                rowSpacing: 4
                Label { text: "X"; color: "#64748B" }
                Label { text: "Y"; color: "#64748B" }
                Label { text: "Largura"; color: "#64748B" }
                Label { text: "Altura"; color: "#64748B" }
                TextField { id: roleX; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                TextField { id: roleY; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                TextField { id: roleW; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
                TextField { id: roleH; Layout.fillWidth: true; inputMethodHints: Qt.ImhFormattedNumbersOnly }
            }
            Button {
                Layout.fillWidth: true
                text: "Aplicar área interna"
                enabled: panel.activeManualSlotId !== "" && roleX.text !== "" && roleY.text !== "" && roleW.text !== "" && roleH.text !== ""
                onClicked: sceneBridge.dispatch(JSON.stringify({
                    "name":"set_item_slot_role_bounds",
                    "slot_id": panel.activeManualSlotId,
                    "role": String(roleCombo.currentValue || "image"),
                    "x": Number(roleX.text),
                    "y": Number(roleY.text),
                    "width": Number(roleW.text),
                    "height": Number(roleH.text)
                }))
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: "#E2E8F0" }
            Label { text: "Salvar slot como modelo"; color: "#475569"; font.bold: true; font.pixelSize: 10 }
            RowLayout {
                Layout.fillWidth: true
                TextField { id: presetName; Layout.fillWidth: true; placeholderText: "Nome do novo preset" }
                Button {
                    text: "Salvar modelo"
                    enabled: panel.activeManualSlotId !== ""
                    onClicked: {
                        sceneBridge.dispatch(JSON.stringify({"name":"save_item_slot_preset", "slot_id": panel.activeManualSlotId, "preset_name": presetName.text}))
                        presetName.text = ""
                    }
                }
            }

            Item { Layout.fillHeight: true }
            Label {
                Layout.fillWidth: true
                text: "Dica: com o slot selecionado, os 8 handles normais do Editor G2 movem/redimensionam o componente inteiro. Ctrl+D duplica a estrutura sem o produto atual."
                wrapMode: Text.WordWrap
                color: "#64748B"
                font.pixelSize: 10
            }
        }
    }

    FileDialog {
        id: saveDialog
        title: "Salvar projeto SR Scene"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Projeto SR Scene (*.srscene)", "Todos os arquivos (*)"]
        onAccepted: sceneBridge.saveSceneAs(selectedFile.toString())
    }
    FileDialog {
        id: pdfDialog
        title: "Exportar PDF de produção"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Documento PDF (*.pdf)"]
        onAccepted: sceneBridge.exportPdf(selectedFile.toString())
    }
    FileDialog {
        id: pngDialog
        title: "Exportar página atual em PNG"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Imagem PNG (*.png)"]
        onAccepted: sceneBridge.exportPng(selectedFile.toString())
    }
}
