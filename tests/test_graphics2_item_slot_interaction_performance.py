from __future__ import annotations

# Exact-SHA certification contract for the ItemSlot local-preview performance path.
from pathlib import Path

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import create_item_slot, item_slot_snapshot
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package


def _session() -> GraphicsSession:
    document = GraphicsDocument(name="ItemSlot interaction perf")
    document.add_page(GraphicsPage(name="Página 1", width=1080, height=1350))
    return GraphicsSession(document)


@pytest.mark.parametrize("preset_id", ["simples", "destaque", "card"])
def test_commit_item_slot_bounds_is_one_logical_group_commit_and_preserves_relative_children(preset_id: str) -> None:
    session = _session()
    slot = create_item_slot(session, preset_id, x=100, y=140)
    router = ItemSlotCommandRouter(session)
    root = session.page.node(str(slot.metadata["root_node_id"]))
    assert root is not None
    before = item_slot_snapshot(session.page, slot)

    result = router.dispatch(
        {
            "name": "commit_item_slot_bounds",
            "slot_id": slot.id,
            "x": root.transform.x + 37,
            "y": root.transform.y + 29,
            "width": root.transform.width * 1.18,
            "height": root.transform.height * 1.13,
        }
    )

    assert result.ok is True
    assert result.changed is True
    after = item_slot_snapshot(session.page, slot)
    assert after["bounds"] == result.payload["bounds"]
    assert after["preset_id"] == before["preset_id"]
    assert after["price_block"] == before["price_block"]
    assert set(after["internal_roles"]) == set(before["internal_roles"])
    for role in before["internal_roles"]:
        before_relative = before["internal_roles"][role]["relative"]
        after_relative = after["internal_roles"][role]["relative"]
        assert after_relative == pytest.approx(before_relative, abs=1e-9)

    assert session.undo() is True
    undone_slot = session.page.slots[slot.id]
    assert item_slot_snapshot(session.page, undone_slot) == before
    assert session.redo() is True
    redone_slot = session.page.slots[slot.id]
    assert item_slot_snapshot(session.page, redone_slot) == after


@pytest.mark.parametrize("preset_id", ["simples", "destaque", "card"])
def test_commit_item_slot_bounds_save_reopen_preserves_final_geometry(tmp_path: Path, preset_id: str) -> None:
    session = _session()
    slot = create_item_slot(session, preset_id, x=90, y=120)
    router = ItemSlotCommandRouter(session)
    root = session.page.node(str(slot.metadata["root_node_id"]))
    assert root is not None
    result = router.dispatch(
        {
            "name": "commit_item_slot_bounds",
            "slot_id": slot.id,
            "x": root.transform.x + 51,
            "y": root.transform.y + 43,
            "width": root.transform.width * 1.2,
            "height": root.transform.height * 1.15,
        }
    )
    assert result.ok and result.changed
    expected = item_slot_snapshot(session.page, slot)

    package = tmp_path / f"{preset_id}-interaction.srscene"
    save_package(session.document, package, embed_local_assets=True)
    reopened = load_package(package, extract_assets_to=tmp_path / f"{preset_id}-assets")
    restored_slot = reopened.active_page.slots[slot.id]
    actual = item_slot_snapshot(reopened.active_page, restored_slot)

    assert actual["bounds"] == expected["bounds"]
    assert actual["internal_roles"] == expected["internal_roles"]
    assert actual["preset_id"] == expected["preset_id"]


def test_qml_manual_item_slot_uses_local_subtree_preview_and_one_release_command() -> None:
    qml = Path("src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    assert "property bool itemSlotPreviewActive: false" in qml
    assert "function itemSlotDisplayTransform(node)" in qml
    assert "property var displayTransform: window.itemSlotDisplayTransform(modelData)" in qml
    assert "property bool slotEditActive: isManualItemSlot || smartSlotEditMode" in qml
    assert 'var commandName = isManualItemSlot ? "commit_item_slot_bounds" : "adjust_smart_slot"' in qml
    assert "window.itemSlotBackendCommits += 1" in qml
    assert "drag.target: window.manualItemSlotForNode(modelData.id) ? null : parent" in qml
    assert "!window.manualItemSlotForNode(anchorNode.id)" in qml
    assert "if (slotMetadata.manual_item_slot)" in qml
    assert "root_node_id" in qml
    assert "property bool resizePreviewKeepsInteractionGeometry:" in qml
    assert "property var interactionBounds: resizePreviewKeepsInteractionGeometry ? bounds : displayBounds" in qml
    assert "x: interactionBounds.x * zoom" in qml
    assert "slotOverlay.displayBounds.x - slotOverlay.interactionBounds.x" in qml
    assert "manualItemSlotResizeHandler" not in qml
