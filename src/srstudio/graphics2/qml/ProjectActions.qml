import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Rectangle {
    id: panel
    width: 512
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

        ToolButton {
            text: "Copiar"
            enabled: !sceneBridge.busy
            ToolTip.text: "Copiar seleção · Ctrl+C"
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
