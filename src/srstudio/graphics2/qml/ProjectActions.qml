import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Rectangle {
    id: panel
    width: 520
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

    RowLayout {
        anchors.fill: parent
        anchors.margins: 5
        spacing: 5

        ToolButton {
            text: "+ Página"
            enabled: !sceneBridge.busy
            ToolTip.text: "Adicionar uma nova página ao encarte"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name": "add_page"}))
        }
        ToolButton {
            text: "Duplicar pág."
            enabled: !sceneBridge.busy
            ToolTip.text: "Duplicar a página atual preservando o layout com identidades internas seguras"
            ToolTip.visible: hovered
            onClicked: sceneBridge.dispatch(JSON.stringify({"name": "duplicate_page"}))
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
