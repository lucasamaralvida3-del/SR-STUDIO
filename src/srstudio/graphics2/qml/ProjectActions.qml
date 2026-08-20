import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window

Rectangle {
    id: panel
    StudioTheme { id: theme }

    anchors.left: parent ? parent.left : undefined
    anchors.right: parent ? parent.right : undefined
    anchors.top: parent ? parent.top : undefined
    anchors.leftMargin: {
        var window = panel.Window.window
        return window && window.studioLeftDockWidth !== undefined ? Number(window.studioLeftDockWidth) : 408
    }
    height: theme.toolBarHeight
    z: 897000
    color: theme.surface
    border.width: 0

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

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: theme.border
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 5

        ToolButton {
            text: "↶"
            enabled: scene.editor ? scene.editor.can_undo : false
            ToolTip.text: "Desfazer"
            ToolTip.visible: hovered
            onClicked: sceneBridge.undo()
        }
        ToolButton {
            text: "↷"
            enabled: scene.editor ? scene.editor.can_redo : false
            ToolTip.text: "Refazer"
            ToolTip.visible: hovered
            onClicked: sceneBridge.redo()
        }
        ToolSeparator {}

        Rectangle {
            implicitWidth: 66
            implicitHeight: 42
            radius: theme.radiusSmall
            color: theme.primarySoft
            Column {
                anchors.centerIn: parent
                spacing: 1
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "➤"; color: theme.primary; font.pixelSize: 13; font.bold: true }
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "Selecionar"; color: theme.primary; font.pixelSize: theme.fontTiny; font.bold: true }
            }
        }
        Rectangle {
            implicitWidth: 54
            implicitHeight: 42
            color: "transparent"
            Column {
                anchors.centerIn: parent
                spacing: 1
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "✥"; color: theme.textMuted; font.pixelSize: 13 }
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "Mover"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
            }
            ToolTip.text: "Mover diretamente no canvas"
            ToolTip.visible: moveHint.containsMouse
            MouseArea { id: moveHint; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }
        Rectangle {
            implicitWidth: 72
            implicitHeight: 42
            color: "transparent"
            Column {
                anchors.centerIn: parent
                spacing: 1
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "↗"; color: theme.textMuted; font.pixelSize: 13 }
                Label { anchors.horizontalCenter: parent.horizontalCenter; text: "Redimensionar"; color: theme.textMuted; font.pixelSize: theme.fontTiny }
            }
            ToolTip.text: "Use os 8 handles da seleção"
            ToolTip.visible: resizeHint.containsMouse
            MouseArea { id: resizeHint; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }

        ToolButton {
            text: "Copiar"
            visible: !(panel.Window.window && panel.Window.window.tightUi)
            enabled: !sceneBridge.busy
            ToolTip.text: "Copiar seleção · Ctrl+C"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"copy"}')
        }
        ToolButton {
            text: "Colar"
            visible: !(panel.Window.window && panel.Window.window.tightUi)
            enabled: !sceneBridge.busy
            ToolTip.text: "Colar seleção · Ctrl+V"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"paste"}')
        }
        ToolButton { text: "Agrupar"; onClicked: sceneBridge.dispatch('{"name":"group"}') }
        ToolButton {
            text: "Alinhar"
            onClicked: alignMenu.open()
            Menu {
                id: alignMenu
                y: parent.height
                MenuItem { text: "Esquerda"; onTriggered: sceneBridge.dispatch('{"name":"align","mode":"left"}') }
                MenuItem { text: "Centro"; onTriggered: sceneBridge.dispatch('{"name":"align","mode":"center"}') }
                MenuItem { text: "Direita"; onTriggered: sceneBridge.dispatch('{"name":"align","mode":"right"}') }
                MenuSeparator {}
                MenuItem { text: "Topo"; onTriggered: sceneBridge.dispatch('{"name":"align","mode":"top"}') }
                MenuItem { text: "Meio"; onTriggered: sceneBridge.dispatch('{"name":"align","mode":"middle"}') }
                MenuItem { text: "Base"; onTriggered: sceneBridge.dispatch('{"name":"align","mode":"bottom"}') }
            }
        }
        ToolButton {
            text: "Distribuir"
            onClicked: distributeMenu.open()
            Menu {
                id: distributeMenu
                y: parent.height
                MenuItem { text: "Horizontal"; onTriggered: sceneBridge.dispatch('{"name":"distribute","axis":"horizontal"}') }
                MenuItem { text: "Vertical"; onTriggered: sceneBridge.dispatch('{"name":"distribute","axis":"vertical"}') }
            }
        }

        ToolSeparator {}
        ToolButton { text: "+ Página"; enabled: !sceneBridge.busy; onClicked: sceneBridge.dispatch('{"name":"add_page"}') }
        ToolButton {
            text: "+ Slot"
            enabled: !sceneBridge.busy
            ToolTip.text: "Adicionar Slot de Item usando presets existentes"
            ToolTip.visible: hovered
            onClicked: presetMenu.open()
        }

        Item { Layout.fillWidth: true }
        BusyIndicator { running: sceneBridge.busy; visible: running; implicitWidth: 22; implicitHeight: 22 }

        Button {
            text: "Compartilhar"
            enabled: false
            ToolTip.text: "Compartilhamento ainda não possui backend no host G2"
            ToolTip.visible: hovered
        }
        Button {
            text: "Salvar"
            enabled: !sceneBridge.busy
            onClicked: saveDialog.open()
        }
        ToolButton {
            text: "↺"
            enabled: !sceneBridge.busy
            ToolTip.text: "Restaurar o ponto de autosave mais recente"
            ToolTip.visible: hovered
            onClicked: sceneBridge.recoverLatest()
        }
        Button {
            text: "Exportar"
            enabled: !sceneBridge.busy
            onClicked: exportMenu.open()
            Menu {
                id: exportMenu
                y: parent.height
                MenuItem { text: "Exportar PDF"; onTriggered: pdfDialog.open() }
                MenuItem { text: "Exportar PNG"; onTriggered: pngDialog.open() }
            }
        }
        Button {
            id: publishButton
            text: "Publicar"
            enabled: false
            opacity: 0.72
            ToolTip.text: "Publicação ainda não possui backend no host G2"
            ToolTip.visible: hovered
            contentItem: Text {
                text: publishButton.text
                color: "white"
                font.pixelSize: theme.fontButton
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: theme.radiusSmall
                color: theme.primary
            }
        }
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
        background: Rectangle { color: theme.surface; border.color: theme.borderStrong; radius: theme.radiusLarge }

        ColumnLayout {
            anchors.fill: parent
            spacing: 9

            RowLayout {
                Layout.fillWidth: true
                Label { text: "EDITAR SLOT DE ITEM"; font.bold: true; font.pixelSize: 16; color: theme.text }
                Item { Layout.fillWidth: true }
                ToolButton { text: "×"; onClicked: itemSlotPopup.close() }
            }
            Label {
                Layout.fillWidth: true
                text: "Ajuste IMAGE, NAME, PRICE e UNIT separadamente. Alterar uma área não deforma as demais."
                wrapMode: Text.WordWrap
                color: theme.textMuted
                font.pixelSize: theme.fontSmall
            }

            Label { text: "Slot atual"; color: theme.textMuted; font.bold: true; font.pixelSize: theme.fontSmall }
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

            Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
            Label { text: "Área interna"; color: theme.textMuted; font.bold: true; font.pixelSize: theme.fontSmall }
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
                Label { text: "X"; color: theme.textMuted }
                Label { text: "Y"; color: theme.textMuted }
                Label { text: "Largura"; color: theme.textMuted }
                Label { text: "Altura"; color: theme.textMuted }
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

            Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
            Label { text: "Salvar slot como modelo"; color: theme.textMuted; font.bold: true; font.pixelSize: theme.fontSmall }
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
                text: "Com o slot selecionado, os 8 handles do Editor G2 continuam movendo e redimensionando o componente inteiro."
                wrapMode: Text.WordWrap
                color: theme.textMuted
                font.pixelSize: theme.fontSmall
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
