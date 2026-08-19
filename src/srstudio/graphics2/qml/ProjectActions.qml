import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window

Rectangle {
    id: panel
    width: 1020
    height: 42
    anchors.left: parent ? parent.left : undefined
    anchors.top: parent ? parent.top : undefined
    anchors.leftMargin: 300
    anchors.topMargin: 7
    z: 897000
    radius: 8
    color: "#FFFFFFF5"
    border.width: 1
    border.color: "#CBD5E1"

    property var scene: ({})
    property bool importingPptx: false
    property url pendingImportFile: ""

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

    Timer {
        id: importPptxTimer
        interval: 1
        repeat: false
        onTriggered: {
            var result = ({"ok": false, "message": "Não foi possível importar este arquivo PPTX."})
            try {
                result = JSON.parse(sceneBridge.dispatch(JSON.stringify({
                    "name": "import_pptx",
                    "path": panel.pendingImportFile.toString()
                })))
            } catch (error) {
                result = ({"ok": false, "message": "Não foi possível importar este arquivo PPTX."})
            }
            panel.importingPptx = false
            panel.pendingImportFile = ""
            panel.refreshScene()
            if (!result.ok) {
                importErrorDialog.text = result.message || "Não foi possível importar este arquivo PPTX."
                importErrorDialog.open()
            }
        }
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
            enabled: !sceneBridge.busy && !panel.importingPptx && panel.pageCount() > 0
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
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Adicionar página"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"add_page"}')
        }
        ToolButton {
            text: "⧉"
            enabled: !sceneBridge.busy && !panel.importingPptx && panel.pageCount() > 0
            ToolTip.text: "Duplicar página com IDs internos seguros"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"duplicate_page"}')
        }
        ToolButton {
            text: "←"
            enabled: !sceneBridge.busy && !panel.importingPptx && panel.activePageIndex() > 0
            ToolTip.text: "Mover página para a esquerda"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name":"reorder_page", "page_id": panel.scene.active_page_id || "", "mode":"previous"}))
        }
        ToolButton {
            text: "→"
            enabled: !sceneBridge.busy && !panel.importingPptx && panel.activePageIndex() >= 0 && panel.activePageIndex() < panel.pageCount() - 1
            ToolTip.text: "Mover página para a direita"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name":"reorder_page", "page_id": panel.scene.active_page_id || "", "mode":"next"}))
        }
        ToolButton {
            text: "×"
            enabled: !sceneBridge.busy && !panel.importingPptx && panel.pageCount() > 1
            ToolTip.text: panel.pageCount() > 1 ? "Excluir página atual · desfazer disponível" : "O projeto precisa manter uma página"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name":"delete_page", "page_id": panel.scene.active_page_id || ""}))
        }
        ToolSeparator {}
        ToolButton {
            text: "Copiar"
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Copiar seleção · preserva ProductCard/PriceBlock/SmartSlot · Ctrl+C"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"copy"}')
        }
        ToolButton {
            text: "Colar"
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Colar preservando ProductCard/PriceBlock/SmartSlot · Ctrl+V"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch('{"name":"paste"}')
        }
        ToolSeparator {}
        ToolButton {
            text: "Importar PPTX / Canva"
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Importe um PowerPoint ou um projeto exportado do Canva em .pptx"
            ToolTip.visible: hovered
            onClicked: importPptxDialog.open()
        }
        ToolButton {
            text: "💾 Salvar"
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Salvar projeto portátil .srscene · Ctrl+S"
            ToolTip.visible: hovered
            onClicked: saveDialog.open()
        }
        ToolButton {
            text: "↺ Recuperar"
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Restaurar o ponto de autosave mais recente deste projeto"
            ToolTip.visible: hovered
            onClicked: sceneBridge.recoverLatest()
        }
        ToolButton {
            text: "PDF"
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Exportar todas as páginas em PDF de produção"
            ToolTip.visible: hovered
            onClicked: pdfDialog.open()
        }
        ToolButton {
            text: "PNG"
            enabled: !sceneBridge.busy && !panel.importingPptx
            ToolTip.text: "Exportar a página atual em PNG de alta resolução"
            ToolTip.visible: hovered
            onClicked: pngDialog.open()
        }
        Item { Layout.fillWidth: true }
        BusyIndicator {
            running: sceneBridge.busy || panel.importingPptx
            visible: running
            implicitWidth: 24
            implicitHeight: 24
        }
    }

    FileDialog {
        id: importPptxDialog
        title: "Importar PPTX / Canva"
        fileMode: FileDialog.OpenFile
        nameFilters: ["PowerPoint (*.pptx)"]
        onAccepted: {
            panel.pendingImportFile = selectedFile
            panel.importingPptx = true
            importPptxTimer.start()
        }
    }

    MessageDialog {
        id: importErrorDialog
        title: "Importar PPTX / Canva"
        text: "Não foi possível importar este arquivo PPTX."
        buttons: MessageDialog.Ok
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
