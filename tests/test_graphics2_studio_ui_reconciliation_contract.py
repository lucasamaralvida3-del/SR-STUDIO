from __future__ import annotations

from pathlib import Path


QML_DIR = Path("src/srstudio/graphics2/qml")
EDITOR = QML_DIR / "GraphicsEditor.qml"


def test_studio_ui_primitives_are_ported_and_wired() -> None:
    for name in (
        "StudioTheme.qml",
        "StudioSidebar.qml",
        "StudioChip.qml",
        "ProductListItem.qml",
        "InspectorSection.qml",
    ):
        assert (QML_DIR / name).is_file(), name

    qml = EDITOR.read_text(encoding="utf-8")
    assert "StudioTheme { id: theme }" in qml
    assert "StudioSidebar {" in qml
    assert "StudioChip {" in qml
    assert "ProductListItem {" in qml
    assert "InspectorSection {" in qml
    assert 'property string leftSection: "Produtos"' in qml
    assert 'text: "Importados da planilha"' in qml
    assert "id: workspaceHeader" in qml
    assert "id: inspector" in qml
    assert "id: zoomBar" in qml


def test_studio_ui_has_responsive_breakpoints_for_supported_viewports() -> None:
    qml = EDITOR.read_text(encoding="utf-8")
    assert "readonly property bool compactUi: width < 1500" in qml
    assert "readonly property bool tightUi: width < 1320" in qml
    assert "studioLeftDockWidth" in qml
    assert "studioInspectorWidth" in qml
    assert "SplitView.minimumWidth: 420" in qml


def test_itemslot_local_preview_contract_survives_ui_reconciliation() -> None:
    qml = EDITOR.read_text(encoding="utf-8")
    required = (
        "property bool itemSlotPreviewActive: false",
        'property string itemSlotPreviewSlotId: ""',
        "property var itemSlotPreviewStartBounds:",
        "property var itemSlotPreviewBounds:",
        "function manualItemSlotForNode(nodeId)",
        "function itemSlotDisplayTransform(node)",
        "property var displayTransform: window.itemSlotDisplayTransform(modelData)",
        "property var interactionBounds: resizePreviewKeepsInteractionGeometry ? bounds : displayBounds",
        "drag.target: window.manualItemSlotForNode(modelData.id) ? null : parent",
        'objectName: "smartSlotResizeArea-"',
        'var commandName = isManualItemSlot ? "commit_item_slot_bounds" : "adjust_smart_slot"',
        "window.itemSlotBackendCommits += 1",
        "!window.manualItemSlotForNode(anchorNode.id)",
    )
    for marker in required:
        assert marker in qml, marker

    queue_region = qml[qml.index("function queuePreview"): qml.index("function commitPreview")]
    assert "sceneBridge.dispatch" not in queue_region
    assert "slotOverlay.queuePreview" not in queue_region

    move_region = qml[qml.index("id: slotMoveArea"): qml.index("Repeater {", qml.index("id: slotMoveArea"))]
    assert "slotOverlay.queuePreview" in move_region
    assert "sceneBridge.dispatch" not in move_region

    resize_region_start = qml.index('objectName: "smartSlotResizeArea-"')
    resize_region = qml[resize_region_start: qml.index("id: selectionOverlay")]
    assert "slotOverlay.queuePreview(resizedBounds(point.x, point.y, mouse.modifiers), false)" in resize_region
    assert 'slotOverlay.commitPreview(resizedBounds(point.x, point.y, mouse.modifiers), "resize")' in resize_region
