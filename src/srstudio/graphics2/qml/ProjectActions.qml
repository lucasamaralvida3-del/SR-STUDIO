import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window

Rectangle {
    id: panel
    width: 890
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

    function refreshScene() {
        try {
            scene = JSON.parse(sceneBridge.sceneJson)
        } catch (error) {
            scene = ({})
        }
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

    Connections {
        target: sceneBridge
        function onSceneChanged() { panel.refreshScene() }
    }

    Connections {
        target: panel.Window.window
        function onClosing(close) {
            // O host atual já possui flush síncrono e portátil. Se o disco não
            // aceitar o recovery final, não permita perda silenciosa do projeto.
            sceneBridge.flushAutosave()
            if (String(sceneBridge.status || "").indexOf("Falha no autosave final:") === 0)
                close.accepted = false
        }
    }

    Component.onCompleted: refreshScene()

    Shortcut {
        sequence: StandardKey.Save
        onActivated: saveDialog.open()
    }
    Shortcut {
        sequence: StandardKey.Copy
        onActivated: sceneBridge.dispatch('{"name":"copy"}')
    }
    Shortcut {
        sequence: StandardKey.Paste
        onActivated: sceneBridge.dispatch('{"name":"paste"}')
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 5

        Label {
            text: "Página"
            color: "#475569"
            font.bold: true
            font.pixelSize: 10
        }
        ComboBox {
            id: pageCombo
            Layout.preferredWidth: 128
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
        ToolButton {
            text: "+"
            enabled: !sceneBridge.busy
            ToolTip.text: "Adicionar página"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"add_page"}')
        }
        ToolButton {
            text: "⧉"
            enabled: !sceneBridge.busy && panel.pageCount() > 0
            ToolTip.text: "Duplicar página com IDs internos seguros"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"duplicate_page"}')
        }
        ToolButton {
            text: "←"
            enabled: !sceneBridge.busy && panel.activePageIndex() > 0
            ToolTip.text: "Mover página para a esquerda"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name":"reorder_page", "page_id": panel.scene.active_page_id || "", "mode":"previous"}))
        }
        ToolButton {
            text: "→"
            enabled: !sceneBridge.busy && panel.activePageIndex() >= 0 && panel.activePageIndex() < panel.pageCount() - 1
            ToolTip.text: "Mover página para a direita"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name":"reorder_page", "page_id": panel.scene.active_page_id || "", "mode":"next"}))
        }
        ToolButton {
            text: "×"
            enabled: !sceneBridge.busy && panel.pageCount() > 1
            ToolTip.text: panel.pageCount() > 1 ? "Excluir página atual · desfazer disponível" : "O projeto precisa manter uma página"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name":"delete_page", "page_id": panel.scene.active_page_id || ""}))
        }
        ToolSeparator {}
        ToolButton {
            text: "Copiar"
            enabled: !sceneBridge.busy
            ToolTip.text: "Copiar seleção · preserva ProductCard/PriceBlock/SmartSlot · Ctrl+C"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"copy"}')
        }
        ToolButton {
            text: "Colar"
            enabled: !sceneBridge.busy
            ToolTip.text: "Colar preservando ProductCard/PriceBlock/SmartSlot · Ctrl+V"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"paste"}')
        }
        ToolSeparator {}
        ToolButton {
            text: "💾 Salvar"
            enabled: !sceneBridge.busy
            ToolTip.text: "Salvar projeto portátil .srscene · Ctrl+S"
            ToolTip.visible: hovered
            onClicked: saveDialog.open()
        }
        ToolButton {
            text: "↺ Recuperar"
            enabled: !sceneBridge.busy
            ToolTip.text: "Restaurar o ponto de autosave mais recente deste projeto"
            ToolTip.visible: hovered
            onClicked: sceneBridge.recoverLatest()
        }
        ToolButton {
            text: "PDF"
            enabled: !sceneBridge.busy
            ToolTip.text: "Exportar todas as páginas em PDF de produção"
            ToolTip.visible: hovered
            onClicked: pdfDialog.open()
        }
        ToolButton {
            text: "PNG"
            enabled: !sceneBridge.busy
            ToolTip.text: "Exportar a página atual em PNG de alta resolução"
            ToolTip.visible: hovered
            onClicked: pngDialog.open()
        }
        Item { Layout.fillWidth: true }
        BusyIndicator {
            running: sceneBridge.busy
            visible: running
            implicitWidth: 24
            implicitHeight: 24
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
