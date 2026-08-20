from __future__ import annotations

from pathlib import Path
from time import perf_counter_ns

import pytest

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.smart_slot_manual import set_manual_slot_bounds


@pytest.fixture
def document() -> GraphicsDocument:
    return _document()


def _document() -> GraphicsDocument:
    document = GraphicsDocument(name="Smart Slot Interaction Perf")
    page = GraphicsPage(name="Página 1", width=1080, height=1350)
    document.add_page(page)
    for slot_id, x in (("slot-1", 120.0), ("slot-2", 520.0)):
        image = GraphicsNode(kind=NodeKind.IMAGE, name=f"Imagem {slot_id}", transform=Transform(x=x, y=180, width=180, height=220))
        name = GraphicsNode(kind=NodeKind.TEXT, name=f"Nome {slot_id}", text="PRODUTO", transform=Transform(x=x, y=420, width=220, height=40))
        price = GraphicsNode(kind=NodeKind.TEXT, name=f"Preço {slot_id}", text="12,99", transform=Transform(x=x, y=470, width=160, height=70))
        page.add_node(image)
        page.add_node(name)
        page.add_node(price)
        page.slots[slot_id] = SmartSlot(
            id=slot_id,
            name=f"Slot {slot_id}",
            center=(x + 100, 360),
            roles={
                BindingRole.IMAGE.value: image.id,
                BindingRole.NAME.value: name.id,
                BindingRole.PRICE.value: price.id,
            },
            metadata={"manual_slot": True},
        )
    return document


def _node_snapshot(document: GraphicsDocument) -> dict[str, tuple]:
    return {
        node.id: (
            node.transform.x,
            node.transform.y,
            node.transform.width,
            node.transform.height,
            node.transform.rotation,
            node.z_index,
            node.visible,
            node.locked,
            node.opacity,
            node.text,
            node.asset_id,
            dict(node.style),
        )
        for node in document.active_page.nodes.values()
    }


def test_qml_smart_slot_hot_path_is_preview_only() -> None:
    qml = Path("src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    start = qml.index("                            Repeater {\n                                model: slots()\n")
    end = qml.index("\n                            Item {\n                                id: selectionOverlay", start)
    block = qml[start:end]

    assert "property var preview_bounds" in block
    assert "previewIntervalMs: 16" in block
    assert block.count("onPositionChanged:") >= 2
    assert "drag.target:" not in block
    assert 'isManualItemSlot ? "commit_item_slot_bounds" : "adjust_smart_slot"' in block
    assert "function commitPreview" in block
    assert "function queuePreview" in block
    assert "sceneBridge.dispatch" not in block[: block.index("function commitPreview")]


def test_release_commit_preserves_visual_nodes_updates_overlap_drop_target_and_feedback() -> None:
    document = _document()
    session = GraphicsSession(document)
    before_nodes = _node_snapshot(document)
    before_revision = int(document.active_page.metadata.get("drop_target_revision") or 0)

    applied = set_manual_slot_bounds(session, "slot-1", x=360, y=150, width=240, height=300)

    assert applied == {"x": 360.0, "y": 150.0, "width": 240.0, "height": 300.0}
    slot = document.active_page.slots["slot-1"]
    assert slot.metadata["user_adjusted_bounds"] == applied
    assert slot.metadata["effective_bounds"] == applied
    assert slot.metadata["manual_overlap_count"] == 1
    assert slot.metadata["manual_overlap_slot_ids"] == ["slot-2"]
    assert int(document.active_page.metadata.get("drop_target_revision") or 0) == before_revision + 1
    assert document.metadata["smart_slot_feedback"][-1]["event"] == "manual_slot_adjust"
    assert _node_snapshot(document) == before_nodes


def test_release_commit_router_path_has_one_dispatch_and_no_scene_mutation_before_release(document: GraphicsDocument) -> None:
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    before = document.to_dict()
    start = perf_counter_ns()
    result = router.dispatch(
        {
            "name": "adjust_smart_slot",
            "slot_id": "slot-1",
            "x": 150,
            "y": 170,
            "width": 250,
            "height": 330,
            "snap": False,
        }
    )
    elapsed_ms = (perf_counter_ns() - start) / 1_000_000.0
    assert result.ok and result.changed
    assert elapsed_ms < 250
    assert document.to_dict() != before
