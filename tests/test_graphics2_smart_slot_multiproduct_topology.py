from __future__ import annotations

import argparse
import json
from pathlib import Path

from srstudio.graphics2.model import (
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    GraphicsPage,
    NodeKind,
    SmartSlot,
    Transform,
)
from srstudio.graphics2.smart_slot_detection import consolidate_smart_slot_false_positives


def _node(
    node_id: str,
    kind: NodeKind,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    text: str = "",
    radius: float = 0,
) -> GraphicsNode:
    style = {}
    if kind in {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.PATH}:
        style["fill"] = "#FFFFFF"
    if radius:
        style["radius"] = radius
    return GraphicsNode(
        id=node_id,
        kind=kind,
        name=node_id,
        transform=Transform(x=x, y=y, width=width, height=height),
        text=text,
        style=style,
    )


def _snapshot(document: GraphicsDocument) -> dict:
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


def _add_real_product(page: GraphicsPage, index: int, x: float, y: float) -> SmartSlot:
    image = _node(f"p{index}-image", NodeKind.IMAGE, x + 10, y + 8, 100, 96)
    name = _node(f"p{index}-name", NodeKind.TEXT, x + 8, y + 112, 172, 30, text=f"PRODUTO REAL {index}")
    price_backplate = _node(f"p{index}-price-backplate", NodeKind.RECT, x + 18, y + 148, 150, 66, radius=18)
    price = _node(f"p{index}-price", NodeKind.TEXT, x + 31, y + 157, 100, 40, text=f"{index}9,90")
    unit = _node(f"p{index}-unit", NodeKind.TEXT, x + 124, y + 178, 40, 20, text="/UN")
    badge = _node(f"p{index}-badge", NodeKind.RECT, x + 116, y + 16, 64, 28, radius=14)
    badge_text = _node(f"p{index}-badge-text", NodeKind.TEXT, x + 122, y + 21, 52, 18, text="OFERTA")

    for node in (price_backplate, badge, image, name, price, unit, badge_text):
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
        "bounds": {"x": x, "y": y, "width": 190, "height": 228},
        "metadata": {
            "content_members": [
                price_backplate.id,
                badge.id,
                badge_text.id,
                image.id,
                name.id,
                price.id,
                unit.id,
            ],
            "source_group_id": "",
            "preserve_source_geometry": True,
        },
    }
    return slot


def _add_false_decorative_slot(page: GraphicsPage, index: int, x: float, y: float, parent_slot: SmartSlot) -> SmartSlot:
    # This deliberately copies the topology that caused the manual failure:
    # a rounded price plate + price text close to a real product card, but no
    # independent product image/name identity.
    plate = _node(f"d{index}-rounded-price-plate", NodeKind.RECT, x, y, 142, 60, radius=20)
    price = _node(f"d{index}-price", NodeKind.TEXT, x + 17, y + 9, 98, 38, text="19,90")
    page.add_node(plate)
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
        "bounds": {"x": x, "y": y, "width": 142, "height": 60},
        "metadata": {
            "content_members": [plate.id, price.id],
            "source_group_id": "",
            "preserve_source_geometry": True,
        },
    }
    parent_card = page.metadata["semantic_blocks"][parent_slot.metadata["semantic_product_card_id"]]
    parent_card["metadata"].setdefault("expected_nested_decorative", []).append(slot.id)
    return slot


def build_multiproduct_topology() -> GraphicsDocument:
    page = GraphicsPage(id="page-multiproduct", name="Multiproduto decorativo", width=1080, height=1350)

    # Shared decorative elements intentionally span multiple products and must
    # never become their own Smart Slot.
    shared_banner = _node("shared-top-banner", NodeKind.RECT, 40, 55, 1000, 86, radius=28)
    shared_title = _node("shared-top-title", NodeKind.TEXT, 90, 78, 900, 42, text="OFERTAS DA SEMANA")
    shared_footer = _node("shared-footer", NodeKind.RECT, 40, 1120, 1000, 120, radius=24)
    for node in (shared_banner, shared_title, shared_footer):
        page.add_node(node)

    positions = [(70, 190), (390, 190), (710, 190), (230, 570), (550, 570)]
    for index, (x, y) in enumerate(positions, start=1):
        real = _add_real_product(page, index, x, y)
        _add_false_decorative_slot(page, index, x + 20, y + 151, real)

    return GraphicsDocument(
        id="doc-multiproduct",
        name="Multiproduto decorativo",
        pages=[page],
        active_page_id=page.id,
    )


def measure_multiproduct_topology() -> dict:
    document = build_multiproduct_topology()
    before_nodes = _snapshot(document)
    report = consolidate_smart_slot_false_positives(document)
    metrics = report.page_metrics[0]

    result = {
        "fixture": "5 real products + 5 decorative false slots",
        "topology": {
            "product_images": 5,
            "product_names": 5,
            "price_texts": 10,
            "price_backplates": 10,
            "badges": 5,
            "badge_texts": 5,
            "rounded_rectangles": 17,
            "shared_decorative_elements": 3,
        },
        "smart_slot_count_before": int(metrics["smart_slots_before"]),
        "smart_slot_count_after": int(metrics["smart_slots_after"]),
        "false_positives_before": int(metrics["decorative_false_positives_before"]),
        "false_positives_after": int(metrics["false_positives_after"]),
        "expected_product_candidates": int(metrics["expected_product_candidates"]),
        "visual_nodes_unchanged": _snapshot(document) == before_nodes,
        "remaining_slot_ids": sorted(document.active_page.slots),
    }
    return result


def test_multiproduct_decorative_topology_reduces_ten_slots_to_five_without_visual_mutation():
    result = measure_multiproduct_topology()
    assert result["smart_slot_count_before"] == 10
    assert result["false_positives_before"] == 5
    assert result["expected_product_candidates"] == 5
    assert result["smart_slot_count_after"] == 5
    assert result["false_positives_after"] == 0
    assert result["visual_nodes_unchanged"] is True
    assert result["remaining_slot_ids"] == [f"slot-real-{index}" for index in range(1, 6)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    result = measure_multiproduct_topology()

    # Keep the same hard gate when the file is executed outside pytest.
    assert result["smart_slot_count_before"] == 10, result
    assert result["false_positives_before"] == 5, result
    assert result["smart_slot_count_after"] == 5, result
    assert result["false_positives_after"] == 0, result
    assert result["visual_nodes_unchanged"] is True, result

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
