import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Rectangle {
    id: panel
    width: 790
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

    Component.onCompleted: refreshScene()

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
            Layout.preferredWidth: 150
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
            ToolTip.text: "Adicionar uma nova página ao encarte"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name": "add_page"}))
        }
        ToolButton {
            text: "⧉"
            enabled: !sceneBridge.busy
            ToolTip.text: "Duplicar a página atual com identidades internas seguras"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name": "duplicate_page"}))
        }
        ToolButton {
            text: "🗑"
            enabled: !sceneBridge.busy && panel.pageCount() > 1
            ToolTip.text: panel.pageCount() > 1 ? "Remover a página atual" : "O projeto precisa manter pelo menos uma página"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name": "remove_page", "page_id": panel.scene.active_page_id || ""}))
        }
        Rectangle {
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            Layout.topMargin: 6
            Layout.bottomMargin: 6
            color: "#E2E8F0"
        }
        ToolButton {
            text: "💾 Salvar"
            enabled: !sceneBridge.busy
            ToolTip.text: "Salvar projeto portátil .srscene"
            ToolTip.visible: hovered
            onClicked: saveDialog.open()
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
