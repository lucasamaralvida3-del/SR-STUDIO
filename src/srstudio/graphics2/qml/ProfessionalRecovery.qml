import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: recoveryBar
    width: 332
    height: recovery.recoverable ? 88 : 32
    anchors.right: parent ? parent.right : undefined
    anchors.bottom: parent ? parent.bottom : undefined
    anchors.rightMargin: 352
    anchors.bottomMargin: 18
    z: 899600
    radius: 8
    color: recovery.recoverable ? "#FFF7ED" : "#F8FAFCF0"
    border.width: 1
    border.color: recovery.recoverable ? "#FDBA74" : "#CBD5E1"

    property var recovery: ({})
    property string statusText: "Autosave PRO ativo"

    function send(command) {
        try {
            return JSON.parse(sceneBridge.dispatch(JSON.stringify(command)))
        } catch (error) {
            return {"ok": false, "message": String(error), "command_payload": ({})}
        }
    }

    function refreshRecovery() {
        var response = send({"name":"recovery_status"})
        if (response.ok)
            recovery = response.command_payload || ({})
        statusText = recovery.recoverable ? "Recuperação pendente — autosave pausado" : "Autosave PRO ativo"
    }

    function autosaveTick() {
        if (recovery.recoverable)
            return
        var response = send({"name":"autosave_tick"})
        var payload = response.command_payload || ({})
        if (payload.blocked_by_recovery) {
            refreshRecovery()
            return
        }
        statusText = payload.saved ? "Autosave salvo" : "Autosave PRO ativo"
        refreshRecovery()
    }

    Component.onCompleted: refreshRecovery()

    Timer {
        interval: 30000
        repeat: true
        running: true
        onTriggered: recoveryBar.autosaveTick()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 7
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: recovery.recoverable ? "⚠ Recuperação disponível" : "✓ " + statusText
                font.bold: recovery.recoverable
                font.pixelSize: 10
                color: recovery.recoverable ? "#9A3412" : "#475569"
                Layout.fillWidth: true
            }
        }

        Label {
            visible: !!recovery.recoverable
            Layout.fillWidth: true
            text: "Há um autosave diferente do projeto aberto. Escolha antes de continuar o autosave automático."
            wrapMode: Text.WordWrap
            font.pixelSize: 9
            color: "#7C2D12"
        }

        RowLayout {
            visible: !!recovery.recoverable
            Layout.fillWidth: true
            Button {
                text: "Recuperar"
                Layout.fillWidth: true
                onClicked: {
                    var response = send({"name":"recover_latest_autosave"})
                    if (response.ok) refreshRecovery()
                }
            }
            Button {
                text: "Descartar autosave"
                Layout.fillWidth: true
                onClicked: {
                    var response = send({"name":"discard_autosaves"})
                    if (response.ok) {
                        refreshRecovery()
                        autosaveTick()
                    }
                }
            }
        }
    }
}
