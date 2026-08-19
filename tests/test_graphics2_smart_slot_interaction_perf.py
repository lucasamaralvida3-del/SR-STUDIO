from __future__ import annotations

import json
from pathlib import Path

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.drop_target import find_drop_target
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.smart_slot_manual import mark_slot_non_product, restore_auto_slot_bounds, set_manual_slot_bounds


def _document() -> GraphicsDocument:
    page = GraphicsPage(id="page-perf", name="Perf", width=1080, height=1350)
    for index, x in enumerate((100, 420), start=1):
        image = GraphicsNode(
            id=f"image-{index}",
            kind=NodeKind.IMAGE,
            name=f"Produto {index}",
            transform=Transform(x=x, y=180, width=150, height=160),
        )
        name = GraphicsNode(
            id=f"name-{index}",
            kind=NodeKind.TEXT,
            name=f"Nome {index}",
            text=f"PRODUTO {index}",
            transform=Transform(x=x, y=350, width=180, height=36),
        )
        page.add_node(image)
        page.add_node(name)
        bounds = {"x": float(x - 20), "y": 150.0, "width": 220.0, "height": 280.0}
        slot = SmartSlot(
            id=f"slot-{index}",
            name=f"Slot {index}",
            page_id=page.id,
            node_by_role={BindingRole.IMAGE.value: image.id, BindingRole.NAME.value: name.id},
            metadata={
                "source": "canva-smart-slot",
                "original_detected_bounds": dict(bounds),
                "effective_bounds": dict(bounds),
            },
        )
        page.slots[slot.id] = slot
    return GraphicsDocument(id="doc-perf", name="Perf", pages=[page], active_page_id=page.id)


def _node_snapshot(document: GraphicsDocument) -> dict:
    return {
        node.id: (
            node.kind.value,
            node.name,
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
            dict(node.metadata),
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
    assert block.count('"name":"adjust_smart_slot"') == 1
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
    assert document.active_page.metadata["drop_target_revision"] == before_revision + 1
    assert _node_snapshot(document) == before_nodes
    assert document.metadata["smart_slot_feedback"][-1]["action"] == "manual-bounds"

    target = find_drop_target(document.active_page, 390, 170, magnet_distance=0)
    assert target is not None
    assert target.slot_id == "slot-1"


def test_qml_dispatch_can_skip_duplicate_scene_payload_without_losing_bounds_payload() -> None:
    document = _document()
    router = GraphicsCommandRouter(GraphicsSession(document))
    command = json.dumps(
        {"name": "adjust_smart_slot", "slot_id": "slot-1", "x": 140, "y": 180, "width": 250, "height": 300}
    )

    compact = json.loads(router.dispatch_json(command, include_scene_payload=False))
    assert compact["ok"] is True
    assert compact["changed"] is True
    assert compact["payload"]["slot_id"] == "slot-1"
    assert compact["payload"]["bounds"] == {"x": 140.0, "y": 180.0, "width": 250.0, "height": 300.0}
    assert "pages" not in compact["payload"]


def test_save_reopen_and_restore_auto_keep_final_bounds(tmp_path: Path) -> None:
    document = _document()
    session = GraphicsSession(document)
    set_manual_slot_bounds(session, "slot-1", x=170, y=210, width=260, height=320)

    package = save_package(document, tmp_path / "perf.srscene", embed_local_assets=True)
    reopened = load_package(package)
    reopened_slot = reopened.active_page.slots["slot-1"]
    assert reopened_slot.metadata["user_adjusted_bounds"] == {"x": 170.0, "y": 210.0, "width": 260.0, "height": 320.0}
    assert reopened_slot.metadata["effective_bounds"] == reopened_slot.metadata["user_adjusted_bounds"]

    restored = restore_auto_slot_bounds(GraphicsSession(reopened), "slot-1")
    assert restored == {"x": 80.0, "y": 150.0, "width": 220.0, "height": 280.0}
    assert "user_adjusted_bounds" not in reopened.active_page.slots["slot-1"].metadata


def test_non_product_and_delete_semantics_preserve_visual_nodes() -> None:
    document = _document()
    before_nodes = _node_snapshot(document)
    mark_slot_non_product(GraphicsSession(document), "slot-1", reason="manual-non-product")
    assert "slot-1" not in document.active_page.slots
    assert _node_snapshot(document) == before_nodes
    assert document.metadata["suppressed_smart_slots"][-1]["slot_id"] == "slot-1"
