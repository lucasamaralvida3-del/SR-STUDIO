from __future__ import annotations

from srstudio.graphics2.import_audit import audit_import
from srstudio.graphics2.model import (
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    NodeKind,
    SmartSlot,
    Transform,
)


def test_import_audit_accepts_well_formed_product_slot(tmp_path):
    image = tmp_path / "produto.png"
    image.write_bytes(b"fake")
    document = GraphicsDocument()
    page = document.active_page
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        text="CAFÉ 500G",
        transform=Transform(x=50, y=50, width=300, height=60),
        style={"font_family": "Arial"},
    )
    picture = GraphicsNode(
        kind=NodeKind.IMAGE,
        transform=Transform(x=50, y=120, width=220, height=220),
        metadata={"bound_image_source": str(image)},
    )
    price = GraphicsNode(
        kind=NodeKind.TEXT,
        text="33",
        transform=Transform(x=280, y=220, width=100, height=80),
        style={"font_family": "Arial"},
    )
    page.add_node(name)
    page.add_node(picture)
    page.add_node(price)
    page.slots["slot_1"] = SmartSlot(
        id="slot_1",
        name="Produto 1",
        page_id=page.id,
        node_by_role={
            BindingRole.NAME.value: name.id,
            BindingRole.IMAGE.value: picture.id,
            BindingRole.PRICE_REAIS.value: price.id,
        },
    )
    report = audit_import(document)
    assert report.ready
    assert report.errors == 0
    assert report.slots == 1
    assert report.images == 1
    assert report.texts == 2
    assert document.metadata["graphics2_import_audit"]["ready"] is True


def test_import_audit_flags_missing_asset_and_incomplete_slot(tmp_path):
    document = GraphicsDocument()
    page = document.active_page
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        transform=Transform(x=10, y=10, width=100, height=100),
        metadata={"bound_image_source": str(tmp_path / "missing.png")},
    )
    page.add_node(image)
    page.slots["slot_bad"] = SmartSlot(
        id="slot_bad",
        name="Incompleto",
        page_id=page.id,
        node_by_role={BindingRole.IMAGE.value: image.id},
    )
    report = audit_import(document)
    codes = {issue.code for issue in report.issues}
    assert report.ready
    assert report.warnings >= 3
    assert "IMAGE_FILE_MISSING" in codes
    assert "SLOT_BINDING_MISSING" in codes


def test_import_audit_rejects_slot_referencing_missing_node():
    document = GraphicsDocument()
    page = document.active_page
    page.slots["slot_bad"] = SmartSlot(
        id="slot_bad",
        page_id=page.id,
        node_by_role={
            BindingRole.NAME.value: "node_missing",
            BindingRole.IMAGE.value: "node_missing",
            BindingRole.PRICE_REAIS.value: "node_missing",
        },
    )
    report = audit_import(document, check_local_assets=False)
    assert not report.ready
    assert report.errors == 3
    assert all(issue.code == "SLOT_NODE_MISSING" for issue in report.issues)


def test_import_audit_detects_off_page_element():
    document = GraphicsDocument()
    page = document.active_page
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        text="FORA",
        transform=Transform(x=page.width + 10, y=20, width=100, height=40),
        style={"font_family": "Arial"},
    )
    page.add_node(node)
    report = audit_import(document, check_local_assets=False)
    assert any(issue.code == "OUTSIDE_PAGE" for issue in report.issues)


def test_import_audit_counts_custom_image_masks_and_drawingml_fill_outsets():
    document = GraphicsDocument()
    page = document.active_page
    page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            transform=Transform(x=20, y=20, width=200, height=150),
            style={
                "fit": "cover",
                "fill_rect": {"l": -0.30959, "t": 0, "r": -0.30437, "b": 0},
            },
            metadata={
                "bound_image_source": "https://example.invalid/produto.png",
                "clip_path": {
                    "width": 1000,
                    "height": 1000,
                    "paths": [
                        {
                            "width": 1000,
                            "height": 1000,
                            "commands": [
                                {"op": "M", "points": [[0, 0]]},
                                {"op": "L", "points": [[1000, 0]]},
                                {"op": "L", "points": [[850, 1000]]},
                                {"op": "Z"},
                            ],
                        }
                    ],
                },
            },
        )
    )

    report = audit_import(document, check_local_assets=False)
    payload = report.to_dict()

    assert report.images == 1
    assert report.image_clips == 1
    assert report.drawingml_fill_rects == 1
    assert report.drawingml_fill_outsets == 1
    assert payload["image_clips"] == 1
    assert payload["drawingml_fill_rects"] == 1
    assert payload["drawingml_fill_outsets"] == 1
