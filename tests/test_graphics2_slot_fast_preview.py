from pathlib import Path


def test_slot_uses_transient_live_artwork_preview_without_backend_roundtrips():
    qml = (Path(__file__).resolve().parents[1] /
           "src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    # The entire visual hierarchy, not only the selection border, follows the cursor.
    assert "window.liveSlotNodeRect(modelData)" in qml
    assert "window.activeSlotPreview = pendingPreviewBounds" in qml
    assert "function previewMemberIds(slot)" in qml
    assert "root_node_id" in qml
    assert "meta.decorative_nodes || []" in qml
    assert "meta.source_node_ids || []" in qml
    # Do not round-trip Python on every positionChanged.
    preview = qml.split("function queuePreview(raw, force)", 1)[1].split("function commitPreview", 1)[0]
    assert "sceneBridge.dispatch" not in preview
    assert 'pendingPreviewBounds = force ? snapPreview(raw) : clampPreview(raw)' in preview
    commit = qml.split("function commitPreview(raw, kind)", 1)[1].split("Timer {", 1)[0]
    assert commit.count('sceneBridge.dispatch(') == 1
    assert 'window.clearSlotPreview()' in commit


def test_cancel_clears_transient_transforms():
    qml = (Path(__file__).resolve().parents[1] /
           "src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    # Both move and resize must abandon transient state without persisting it.
    assert qml.count("window.clearSlotPreview()") >= 3
    assert "property var activeSlotPreview: null" in qml
    assert "property var activeSlotPreviewMembers: ({})" in qml
