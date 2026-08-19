from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

from PIL import Image
import pytest

import srstudio
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import (
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    GraphicsPage,
    NodeKind,
    SmartSlot,
    Transform,
)
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.qt_renderer import render_png
from srstudio.graphics2.smart_slot_detection import consolidate_smart_slot_false_positives
from srstudio.graphics2.smart_slot_geometry import refresh_smart_slot_geometry
from srstudio.graphics2.smart_slot_manual import (
    mark_slot_non_product,
    restore_auto_slot_bounds,
    set_manual_slot_bounds,
)


def _node(node_id: str, kind: NodeKind, x: float, y: float, w: float, h: float, *, text: str = "") -> GraphicsNode:
    return GraphicsNode(
        id=node_id,
        kind=kind,
        name=node_id,
        transform=Transform(x=x, y=y, width=w, height=h),
        text=text,
        style={"fill": "#FFFFFF"} if kind in {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.PATH} else {},
    )


def _add_real_product(page: GraphicsPage, index: int, x: float, y: float) -> SmartSlot:
    image = _node(f"p{index}-image", NodeKind.IMAGE, x + 8, y + 8, 92, 94)
    name = _node(f"p{index}-name", NodeKind.TEXT, x + 8, y + 108, 160, 28, text=f"PRODUTO REAL {index}")
    price = _node(f"p{index}-price", NodeKind.TEXT, x + 25, y + 148, 92, 42, text=f"{index}9,90")
    unit = _node(f"p{index}-unit", NodeKind.TEXT, x + 120, y + 165, 38, 20, text="/UN")
    background = _node(f"p{index}-price-bg", NodeKind.RECT, x + 15, y + 140, 150, 62)
    for node in (background, image, name, price, unit):
        page.add_node(node)
    slot = SmartSlot(
        id=f"slot-real-{index}",
        name=f"Produto real {index}",
        page_id=page.id,
        node_by_role={
            BindingRole.IMAGE.value: image.id,
            BindingRole.NAME.value: name.id,
            BindingRole.RETAIL_PRICE.value: price.id,
            BindingRole.UNIT.value: unit.id,
        },
        metadata={
            "source": "canva-smart-slot",
            "semantic_recovered": True,
            "semantic_product_card_id": f"card-real-{index}",
            "semantic_price_block_ids": [],
            "product_snapshot": {},
        },
    )
    page.slots[slot.id] = slot
    page.metadata.setdefault("semantic_blocks", {})[f"card-real-{index}"] = {
        "id": f"card-real-{index}",
        "kind": "product_card",
        "slot_id": slot.id,
        "members": [image.id, name.id, price.id, unit.id],
        "roles": {},
        "bounds": {"x": x, "y": y, "width": 180, "height": 215},
        "metadata": {
            "content_members": [background.id, image.id, name.id, price.id, unit.id],
            "source_group_id": "",
            "preserve_source_geometry": True,
        },
    }
    return slot


def _add_false_decorative_slot(page: GraphicsPage, index: int, x: float, y: float, *, parent_slot: SmartSlot | None = None) -> SmartSlot:
    shape = _node(f"d{index}-shape", NodeKind.RECT, x, y, 138, 58)
    price = _node(f"d{index}-price", NodeKind.TEXT, x + 16, y + 8, 96, 38, text="19,90")
    page.add_node(shape)
    page.add_node(price)
    slot = SmartSlot(
        id=f"slot-decor-{index}",
        name=f"Decorativo {index}",
        page_id=page.id,
        node_by_role={BindingRole.RETAIL_PRICE.value: price.id},
        confidence=0.74,
        metadata={
            "source": "canva-smart-slot",
            "semantic_recovered": True,
            "semantic_product_card_id": f"card-decor-{index}",
            "semantic_price_block_ids": [],
            "product_snapshot": {},
        },
    )
    page.slots[slot.id] = slot
    page.metadata.setdefault("semantic_blocks", {})[f"card-decor-{index}"] = {
        "id": f"card-decor-{index}",
        "kind": "product_card",
        "slot_id": slot.id,
        "members": [price.id],
        "roles": {},
        "bounds": {"x": x, "y": y, "width": 138, "height": 58},
        "metadata": {
            "content_members": [shape.id, price.id],
            "source_group_id": "",
            "preserve_source_geometry": True,
        },
    }
    if parent_slot is not None:
        parent_card = page.metadata["semantic_blocks"][parent_slot.metadata["semantic_product_card_id"]]
        parent_card["metadata"].setdefault("expected_nested_decorative", []).append(slot.id)
    return slot


def _five_product_document(*, with_false_slots: bool = False) -> GraphicsDocument:
    page = GraphicsPage(id="page-five", name="Cinco produtos", width=1080, height=1350)
    positions = [(80, 180), (390, 180), (700, 180), (230, 560), (560, 560)]
    for index, (x, y) in enumerate(positions, start=1):
        real = _add_real_product(page, index, x, y)
        if with_false_slots:
            _add_false_decorative_slot(page, index, x + 18, y + 142, parent_slot=real)
    return GraphicsDocument(id="doc-five", name="Cinco produtos", pages=[page], active_page_id=page.id)


def _node_snapshot(document: GraphicsDocument) -> dict:
    return {
        page.id: {
            node.id: (
                node.kind.value,
                node.transform.x,
                node.transform.y,
                node.transform.width,
                node.transform.height,
                node.transform.rotation,
                node.z_index,
                node.visible,
                node.text,
                node.asset_id,
                dict(node.style),
            )
            for node in page.nodes.values()
        }
        for page in document.pages
    }


def test_case_1_rounded_rect_plus_price_text_does_not_survive_as_smart_slot():
    page = GraphicsPage(id="case1", width=600, height=800)
    shape = _node("rounded", NodeKind.RECT, 100, 300, 180, 70)
    shape.style["radius"] = 22
    price = _node("price", NodeKind.TEXT, 125, 315, 120, 40, text="12,99")
    page.add_node(shape)
    page.add_node(price)
    _add_false_decorative_slot(page, 1, 100, 300)
    document = GraphicsDocument(pages=[page], active_page_id=page.id)
    before_nodes = _node_snapshot(document)

    report = consolidate_smart_slot_false_positives(document)

    assert report.smart_slots_before == 1
    assert report.decorative_false_positives_before == 1
    assert report.smart_slots_after == 0
    assert report.false_positives_after == 0
    assert _node_snapshot(document) == before_nodes


def test_case_2_product_image_name_price_and_background_is_one_smart_slot():
    page = GraphicsPage(id="case2", width=600, height=800)
    _add_real_product(page, 1, 100, 220)
    document = GraphicsDocument(pages=[page], active_page_id=page.id)
    before_nodes = _node_snapshot(document)

    report = consolidate_smart_slot_false_positives(document)

    assert report.smart_slots_before == 1
    assert report.smart_slots_after == 1
    assert report.false_positives_after == 0
    assert len(page.slots) == 1
    assert _node_snapshot(document) == before_nodes


def test_case_3_contained_decorative_shape_becomes_existing_card_member():
    page = GraphicsPage(id="case3", width=600, height=800)
    real = _add_real_product(page, 1, 100, 220)
    false_slot = _add_false_decorative_slot(page, 1, 118, 362, parent_slot=real)
    shape_id = "d1-shape"
    document = GraphicsDocument(pages=[page], active_page_id=page.id)
    before = _node_snapshot(document)

    report = consolidate_smart_slot_false_positives(document)

    assert false_slot.id not in page.slots
    assert real.id in page.slots
    real_card = page.metadata["semantic_blocks"]["card-real-1"]
    assert shape_id in real_card["metadata"]["content_members"]
    assert page.nodes[shape_id].metadata["decorative_card_member"] is True
    assert report.merged_decorative_members >= 1
    assert report.false_positives_after == 0
    assert _node_snapshot(document) == before


def test_case_4_five_products_with_graphic_backgrounds_stay_five_not_ten():
    document = _five_product_document(with_false_slots=True)
    page = document.active_page
    before_nodes = _node_snapshot(document)

    report = consolidate_smart_slot_false_positives(document)

    metrics = report.page_metrics[0]
    assert metrics["smart_slots_before"] == 10
    assert metrics["decorative_false_positives_before"] == 5
    assert metrics["expected_product_candidates"] == 5
    assert metrics["smart_slots_after"] == 5
    assert metrics["false_positives_after"] == 0
    assert len(page.slots) == 5
    assert _node_snapshot(document) == before_nodes


def test_manual_resize_save_close_reopen_preserves_user_bounds(tmp_path):
    document = _five_product_document()
    refresh_smart_slot_geometry(document)
    session = GraphicsSession(document)
    slot = document.active_page.slots["slot-real-1"]
    auto = dict(slot.metadata["original_detected_bounds"])
    target = {
        "x": auto["x"] + 11,
        "y": auto["y"] + 7,
        "width": auto["width"] + 23,
        "height": auto["height"] + 19,
    }

    set_manual_slot_bounds(session, slot.id, **target)
    package = save_package(document, tmp_path / "manual-slot.srscene", embed_local_assets=False)
    reopened = load_package(package)
    refresh_smart_slot_geometry(reopened)
    restored = reopened.active_page.slots[slot.id]

    assert restored.metadata["adjustment_source"] == "manual"
    assert restored.metadata["user_adjusted_bounds"] == target
    assert restored.metadata["effective_bounds"] == target
    assert restored.metadata["original_detected_bounds"] == auto


def test_manual_slot_move_does_not_change_export_pixels(tmp_path):
    QtGui = pytest.importorskip("PySide6.QtGui")
    QGuiApplication = QtGui.QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(["smart-slot-manual-export"])
    assert app is not None
    document = _five_product_document()
    refresh_smart_slot_geometry(document)
    before_nodes = _node_snapshot(document)
    before_png = tmp_path / "before.png"
    after_png = tmp_path / "after.png"
    # This fixture intentionally uses synthetic IMAGE nodes without local
    # assets. Asset strictness is covered by export tests; here the invariant is
    # that semantic Smart Slot geometry cannot change rendered pixels.
    render_png(document, before_png, page_index=0, dpi=96, strict_assets=False)

    session = GraphicsSession(document)
    slot = document.active_page.slots["slot-real-1"]
    auto = dict(slot.metadata["effective_bounds"])
    set_manual_slot_bounds(
        session,
        slot.id,
        x=auto["x"] + 37,
        y=auto["y"] + 29,
        width=auto["width"],
        height=auto["height"],
    )
    render_png(document, after_png, page_index=0, dpi=96, strict_assets=False)

    with Image.open(before_png) as before_image, Image.open(after_png) as after_image:
        assert before_image.size == after_image.size
        assert before_image.tobytes() == after_image.tobytes()
    assert _node_snapshot(document) == before_nodes


def test_manual_mark_non_product_survives_save_reopen_without_returning(tmp_path):
    document = _five_product_document(with_false_slots=True)
    refresh_smart_slot_geometry(document)
    session = GraphicsSession(document)
    false_slot_id = "slot-decor-1"
    assert false_slot_id in document.active_page.slots

    mark_slot_non_product(session, false_slot_id)
    package = save_package(document, tmp_path / "suppressed-slot.srscene", embed_local_assets=False)
    reopened = load_package(package)
    refresh_smart_slot_geometry(reopened)

    assert false_slot_id not in reopened.active_page.slots
    assert any(item.get("slot_id") == false_slot_id for item in reopened.metadata["suppressed_smart_slots"])
    assert any(item.get("false_positive") is True for item in reopened.metadata["smart_slot_feedback"])


def test_restore_auto_returns_exactly_to_original_detected_bounds():
    document = _five_product_document()
    refresh_smart_slot_geometry(document)
    session = GraphicsSession(document)
    slot = document.active_page.slots["slot-real-1"]
    original = dict(slot.metadata["original_detected_bounds"])
    set_manual_slot_bounds(
        session,
        slot.id,
        x=original["x"] + 31,
        y=original["y"] + 22,
        width=original["width"] - 9,
        height=original["height"] - 11,
    )

    restored = restore_auto_slot_bounds(session, slot.id)
    refresh_smart_slot_geometry(document)

    assert restored == original
    assert slot.metadata["effective_bounds"] == original
    assert slot.metadata["adjustment_source"] == "auto-restored"
    assert "user_adjusted_bounds" not in slot.metadata


def test_manual_adjustment_of_one_slot_does_not_change_other_slot_bounds():
    document = _five_product_document()
    refresh_smart_slot_geometry(document)
    page = document.active_page
    before = {slot.id: dict(slot.metadata["effective_bounds"]) for slot in page.slots.values()}
    session = GraphicsSession(document)
    first = page.slots["slot-real-1"]
    current = before[first.id]

    set_manual_slot_bounds(
        session,
        first.id,
        x=current["x"] + 12,
        y=current["y"] + 8,
        width=current["width"] + 10,
        height=current["height"] + 6,
    )
    refresh_smart_slot_geometry(document)

    for slot_id, bounds in before.items():
        if slot_id == first.id:
            continue
        assert page.slots[slot_id].metadata["effective_bounds"] == bounds


def test_command_router_exposes_manual_slot_actions_and_structured_feedback():
    document = _five_product_document(with_false_slots=True)
    document.metadata["import_fingerprint_sha256"] = "fingerprint-test"
    refresh_smart_slot_geometry(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    slot = document.active_page.slots["slot-real-1"]
    current = dict(slot.metadata["effective_bounds"])

    result = router.dispatch({
        "name": "adjust_smart_slot",
        "slot_id": slot.id,
        "x": current["x"] + 5,
        "y": current["y"] + 5,
        "width": current["width"],
        "height": current["height"],
        "snap": False,
    })
    assert result.ok and result.changed
    feedback = document.metadata["smart_slot_feedback"][-1]
    assert feedback["source_pptx_fingerprint"] == "fingerprint-test"
    assert set(feedback) >= {
        "auto_bounds",
        "user_bounds",
        "nodes_inside_auto",
        "nodes_inside_user",
        "nodes_removed",
        "nodes_added",
        "false_positive",
        "manual_slot_merge",
        "manual_slot_delete",
        "layout_features",
    }

    false_slot_id = "slot-decor-1"
    result = router.dispatch({"name": "mark_smart_slot_non_product", "slot_id": false_slot_id})
    assert result.ok and result.changed
    assert false_slot_id not in document.active_page.slots


def test_qml_exposes_smart_slot_adjust_mode_without_serializing_overlay_nodes():
    qml = (Path(srstudio.__file__).with_name("graphics2") / "qml" / "GraphicsEditor.qml").read_text(encoding="utf-8")

    assert "property bool smartSlotEditMode: false" in qml
    assert "Ajustar Smart Slot" in qml
    assert '"name":"adjust_smart_slot"' in qml or '"name": "adjust_smart_slot"' in qml
    assert '"name":"restore_smart_slot_auto"' in qml or '"name": "restore_smart_slot_auto"' in qml
    assert '"name":"mark_smart_slot_non_product"' in qml or '"name": "mark_smart_slot_non_product"' in qml
    assert "smartSlotEditMode || smartSlotInspectionMode" in qml


def test_strict_group_name_price_without_third_role_is_not_product():
    page = GraphicsPage(id="strict-group", width=600, height=800)
    shape = _node("strict-shape", NodeKind.RECT, 100, 300, 180, 70)
    name = _node("strict-name", NodeKind.TEXT, 110, 286, 160, 24, text="OFERTA")
    price = _node("strict-price", NodeKind.TEXT, 125, 315, 120, 40, text="12,99")
    for node in (shape, name, price):
        page.add_node(node)
    slot = SmartSlot(
        id="slot-strict-group",
        name="Grupo decorativo",
        page_id=page.id,
        node_by_role={BindingRole.NAME.value: name.id, BindingRole.RETAIL_PRICE.value: price.id},
        metadata={
            "source": "canva-smart-slot",
            "semantic_recovered": True,
            "source_group_id": "drawingml-group-decor",
            "semantic_product_card_id": "card-strict-group",
            "product_snapshot": {},
        },
    )
    page.slots[slot.id] = slot
    page.metadata["semantic_blocks"] = {
        "card-strict-group": {
            "id": "card-strict-group",
            "kind": "product_card",
            "slot_id": slot.id,
            "members": [shape.id, name.id, price.id],
            "roles": {},
            "bounds": {"x": 100, "y": 286, "width": 180, "height": 84},
            "metadata": {"source_group_id": "drawingml-group-decor", "content_members": [shape.id, name.id, price.id]},
        }
    }
    document = GraphicsDocument(pages=[page], active_page_id=page.id)
    before = _node_snapshot(document)

    report = consolidate_smart_slot_false_positives(document)

    assert report.decorative_false_positives_before == 1
    assert report.smart_slots_after == 0
    assert report.false_positives_after == 0
    assert _node_snapshot(document) == before


def test_drop_target_uses_manual_smart_slot_bounds():
    from srstudio.graphics2.drop_target import find_drop_target

    document = _five_product_document()
    refresh_smart_slot_geometry(document)
    session = GraphicsSession(document)
    slot = document.active_page.slots["slot-real-1"]
    original = dict(slot.metadata["effective_bounds"])
    manual = {
        "x": original["x"] + original["width"] + 60,
        "y": original["y"],
        "width": 90,
        "height": 90,
    }
    set_manual_slot_bounds(session, slot.id, **manual)

    target = find_drop_target(
        document.active_page,
        manual["x"] + manual["width"] / 2,
        manual["y"] + manual["height"] / 2,
    )
    assert target is not None
    assert target.slot_id == slot.id
    assert target.bounds.x == manual["x"]
    assert target.bounds.y == manual["y"]
    assert target.bounds.width == manual["width"]
    assert target.bounds.height == manual["height"]