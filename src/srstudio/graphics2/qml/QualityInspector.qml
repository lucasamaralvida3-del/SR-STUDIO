import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    width: 326
    height: expanded ? 528 : 56
    anchors.right: parent ? parent.right : undefined
    anchors.top: parent ? parent.top : undefined
    anchors.rightMargin: 8
    anchors.topMargin: 66
    z: 899000
    radius: 9
    color: "#FFFFFFF8"
    border.width: 1
    border.color: gateReady ? "#86D69B" : blockers > 0 ? "#F0A5A5" : "#E9C46A"

    property var scene: ({})
    property var diagnostics: ({})
    property var gate: ({})
    property var audit: ({})
    property var visual: ({})
    property var mapping: ({})
    property var pptxFidelity: ({})
    property var triage: ({})
    property bool expanded: true
    property bool gateReady: Boolean(gate.ready)
    property int blockers: Number(gate.blockers || 0)
    property int warnings: Number(gate.warnings || 0)

    function percent(value) {
        if (value === undefined || value === null || value === "")
            return "—"
        var number = Number(value)
        if (number <= 1.00001)
            number *= 100
        return number.toFixed(1) + "%"
    }

    function coverageColor(value) {
        var number = Number(value === undefined ? 1 : value)
        return number < 0.80 ? "#B91C1C" : number < 0.95 ? "#A16207" : "#334155"
    }

    function autofitSummary() {
        var shape = Number(pptxFidelity.shape_autofit_nodes || 0)
        var normal = Number(pptxFidelity.normal_autofit_nodes || 0)
        var none = Number(pptxFidelity.no_autofit_nodes || 0)
        if (shape === 0 && normal === 0 && none === 0)
            return "—"
        return "Forma " + shape + " · Texto " + normal + " · Sem " + none
    }

    function effectsSummary() {
        var advanced = Number(gate.pptx_advanced_effects || 0)
        if (advanced <= 0)
            return "—"
        return advanced + " · G" + Number(gate.pptx_gradient_fills || 0) + " · S" + Number(gate.pptx_shadows || 0)
    }

    function topTriageSuspect() {
        if (!triage || !triage.available || !triage.attribution)
            return null
        var regions = triage.attribution.regions || []
        if (regions.length === 0)
            return null
        var suspects = regions[0].suspects || []
        return suspects.length > 0 ? suspects[0] : null
    }

    function triageLabel() {
        var suspect = topTriageSuspect()
        if (!suspect)
            return "Nenhum objeto associado"
        var semantic = String(suspect.binding_role || suspect.kind || "objeto")
        var name = String(suspect.name || suspect.node_id || "sem nome")
        return semantic + " · " + name
    }

    function triageHint() {
        var suspect = topTriageSuspect()
        return suspect ? String(suspect.diagnostic_hint || "") : ""
    }

    function refresh() {
        try {
            scene = JSON.parse(sceneBridge.sceneJson)
        } catch (error) {
            scene = ({})
        }
        diagnostics = scene.editor && scene.editor.diagnostics ? scene.editor.diagnostics : ({})
        gate = diagnostics.production_gate || ({})
        audit = diagnostics.import_audit || ({})
        visual = diagnostics.visual_fidelity || ({})
        mapping = diagnostics.pptx_mapping || ({})
        pptxFidelity = diagnostics.pptx_fidelity || ({})
        triage = diagnostics.visual_fidelity_triage || (scene.metadata && scene.metadata.visual_fidelity_triage_last ? scene.metadata.visual_fidelity_triage_last : ({}))
    }

    Connections {
        target: sceneBridge
        function onSceneChanged() { panel.refresh() }
    }

    Component.onCompleted: refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 9
        spacing: 5

        RowLayout {
            Layout.fillWidth: true
            Rectangle {
                Layout.preferredWidth: 10
                Layout.preferredHeight: 10
                radius: 5
                color: gateReady ? "#16A34A" : blockers > 0 ? "#DC2626" : "#D97706"
            }
            Label {
                text: gateReady ? "Production Gate aprovado" : blockers > 0 ? "Production Gate bloqueado" : "Production Gate em validação"
                color: "#111827"
                font.bold: true
                font.pixelSize: 11
                Layout.fillWidth: true
            }
            Label {
                text: String(Number(gate.score || 0)) + "/100"
                color: gateReady ? "#15803D" : blockers > 0 ? "#B91C1C" : "#A16207"
                font.bold: true
                font.pixelSize: 13
            }
            ToolButton {
                text: expanded ? "▴" : "▾"
                implicitWidth: 28
                implicitHeight: 26
                onClicked: expanded = !expanded
            }
        }

        ColumnLayout {
            visible: expanded
            Layout.fillWidth: true
            spacing: 4

            Rectangle { Layout.fillWidth: true; height: 1; color: "#E2E8F0" }

            GridLayout {
                columns: 2
                columnSpacing: 10
                rowSpacing: 4
                Layout.fillWidth: true

                Label { text: "Estrutural"; color: "#64748B"; font.pixelSize: 9 }
                Label { text: String(Number(gate.structural_score || 0)) + "/100"; color: "#334155"; font.bold: true; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true }

                Label { text: "Confiança importação"; color: "#64748B"; font.pixelSize: 9 }
                Label { text: percent(gate.import_confidence !== undefined ? gate.import_confidence : audit.confidence); color: "#334155"; font.bold: true; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true }

                Label { text: "Fidelidade visual"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: gate.visual_score === null || gate.visual_score === undefined ? "Golden Master pendente" : percent(gate.visual_score)
                    color: gate.visual_passed === false ? "#B91C1C" : gate.visual_passed === true ? "#15803D" : "#64748B"
                    font.bold: true
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Cobertura texto"; color: "#64748B"; font.pixelSize: 9 }
                Label { text: percent(gate.mapping_text_coverage); color: "#334155"; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true }

                Label { text: "Auto-fit PPTX"; color: "#64748B"; font.pixelSize: 9 }
                Label { text: autofitSummary(); color: "#334155"; font.bold: true; font.pixelSize: 9; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true }

                Label { text: "Cobertura auto-fit"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: percent(gate.mapping_autofit_coverage)
                    color: coverageColor(gate.mapping_autofit_coverage)
                    font.bold: Number(gate.mapping_autofit_coverage === undefined ? 1 : gate.mapping_autofit_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Espaço letras"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: percent(gate.mapping_letter_spacing_coverage)
                    color: coverageColor(gate.mapping_letter_spacing_coverage)
                    font.bold: Number(gate.mapping_letter_spacing_coverage === undefined ? 1 : gate.mapping_letter_spacing_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Entrelinhas"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: percent(gate.mapping_line_spacing_coverage)
                    color: coverageColor(gate.mapping_line_spacing_coverage)
                    font.bold: Number(gate.mapping_line_spacing_coverage === undefined ? 1 : gate.mapping_line_spacing_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Cobertura imagens"; color: "#64748B"; font.pixelSize: 9 }
                Label { text: percent(gate.mapping_image_coverage); color: "#334155"; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true }

                Label { text: "Transform. imagens"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: percent(gate.image_transform_coverage)
                    color: coverageColor(gate.image_transform_coverage)
                    font.bold: Number(gate.image_transform_coverage === undefined ? 1 : gate.image_transform_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label {
                    text: "Rotação/flip especial"
                    visible: Number(gate.image_transform_non_identity_contracts || 0) > 0
                    color: "#64748B"
                    font.pixelSize: 9
                }
                Label {
                    visible: Number(gate.image_transform_non_identity_contracts || 0) > 0
                    text: percent(gate.image_transform_non_identity_coverage)
                    color: coverageColor(gate.image_transform_non_identity_coverage)
                    font.bold: Number(gate.image_transform_non_identity_coverage === undefined ? 1 : gate.image_transform_non_identity_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Cobertura fillRect"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: percent(gate.mapping_fill_rect_coverage)
                    color: coverageColor(gate.mapping_fill_rect_coverage)
                    font.bold: Number(gate.mapping_fill_rect_coverage === undefined ? 1 : gate.mapping_fill_rect_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Outset de imagem"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: percent(gate.mapping_fill_outset_coverage)
                    color: coverageColor(gate.mapping_fill_outset_coverage)
                    font.bold: Number(gate.mapping_fill_outset_coverage === undefined ? 1 : gate.mapping_fill_outset_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Máscaras imagem"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: percent(gate.mapping_image_clip_coverage)
                    color: coverageColor(gate.mapping_image_clip_coverage)
                    font.bold: Number(gate.mapping_image_clip_coverage === undefined ? 1 : gate.mapping_image_clip_coverage) < 0.95
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }

                Label { text: "Cobertura grupos"; color: "#64748B"; font.pixelSize: 9 }
                Label { text: percent(gate.mapping_group_coverage); color: "#334155"; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true }

                Label { text: "Efeitos PPTX"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: effectsSummary()
                    color: Number(gate.pptx_advanced_effects || 0) > 0 ? "#A16207" : "#334155"
                    font.bold: Number(gate.pptx_advanced_effects || 0) > 0
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                    ToolTip.text: "Total · G gradientes · S sombras"
                    ToolTip.visible: hovered
                }

                Label { text: "Alpha DrawingML"; color: "#64748B"; font.pixelSize: 9 }
                Label {
                    text: String(Number(gate.pptx_alpha_modifiers || 0))
                    color: Number(gate.pptx_alpha_modifiers || 0) > 0 ? "#A16207" : "#334155"
                    horizontalAlignment: Text.AlignRight
                    Layout.fillWidth: true
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: triageColumn.implicitHeight + 12
                radius: 6
                color: "#EFF6FF"
                border.width: 1
                border.color: "#BFDBFE"
                visible: Boolean(triage.available) && topTriageSuspect() !== null

                ColumnLayout {
                    id: triageColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 7
                    anchors.rightMargin: 7
                    spacing: 2

                    Label {
                        text: "Causa provável · " + triageLabel()
                        color: "#1D4ED8"
                        font.bold: true
                        font.pixelSize: 9
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Label {
                        text: triageHint()
                        color: "#475569"
                        font.pixelSize: 8
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Rectangle {
                    radius: 5
                    color: blockers > 0 ? "#FEE2E2" : "#DCFCE7"
                    implicitWidth: blockerLabel.implicitWidth + 14
                    implicitHeight: 24
                    Label { id: blockerLabel; anchors.centerIn: parent; text: blockers + " bloqueio(s)"; color: blockers > 0 ? "#991B1B" : "#166534"; font.bold: true; font.pixelSize: 9 }
                }
                Rectangle {
                    radius: 5
                    color: warnings > 0 ? "#FEF3C7" : "#F1F5F9"
                    implicitWidth: warningLabel.implicitWidth + 14
                    implicitHeight: 24
                    Label { id: warningLabel; anchors.centerIn: parent; text: warnings + " aviso(s)"; color: warnings > 0 ? "#92400E" : "#475569"; font.bold: true; font.pixelSize: 9 }
                }
                Item { Layout.fillWidth: true }
                Label { text: "GPU " + String(diagnostics.graphics_api_requested || "auto").toUpperCase(); color: "#0F5BD8"; font.bold: true; font.pixelSize: 9 }
            }

            Label {
                Layout.fillWidth: true
                text: gateReady ? "Cena apta no gate de desenvolvimento." : blockers > 0 ? "Corrija os bloqueios antes de habilitar o Engine 2." : "Validação real ainda em andamento."
                color: gateReady ? "#15803D" : blockers > 0 ? "#B91C1C" : "#A16207"
                wrapMode: Text.WordWrap
                font.pixelSize: 9
            }
        }
    }

    PageInspector {
        parent: panel.parent
        visible: panel.parent !== null
    }
}
