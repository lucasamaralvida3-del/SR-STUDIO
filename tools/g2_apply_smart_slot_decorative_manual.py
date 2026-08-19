from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    # A DrawingML GROUP is evidence only when its composition is itself strong.
    # GROUP + one name-like text + price is not enough: this is exactly the
    # common backplate/badge false-positive class from Canva.
    replace_once(
        "src/srstudio/graphics2/smart_slot_detection.py",
        "    group_composition = bool(group_id and has_price and (has_name or real_image))\n",
        "    group_composition = bool(\n"
        "        group_id\n"
        "        and (\n"
        "            (real_image and (has_name or has_price))\n"
        "            or (has_name and has_price and len(roles) >= 3)\n"
        "        )\n"
        "    )\n",
    )

    # The edited semantic area is also the true product drop target. ProductCard
    # source bounds remain only a fallback for old documents without effective
    # Smart Slot geometry.
    replace_once(
        "src/srstudio/graphics2/drop_target.py",
        '''def smart_slot_bounds(page: GraphicsPage, slot: SmartSlot) -> Rect | None:
    """Retorna a área visual mais representativa de um Smart Slot."""

    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
''',
        '''def smart_slot_bounds(page: GraphicsPage, slot: SmartSlot) -> Rect | None:
    """Retorna a área semântica/interativa efetiva de um Smart Slot."""

    candidates: list[object] = []
    if str(slot.metadata.get("adjustment_source") or "") == "manual":
        candidates.append(slot.metadata.get("user_adjusted_bounds"))
    candidates.append(slot.metadata.get("effective_bounds"))
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        width = max(0.0, float(raw.get("width") or 0.0))
        height = max(0.0, float(raw.get("height") or 0.0))
        if width > 0 and height > 0:
            return Rect(
                float(raw.get("x") or 0.0),
                float(raw.get("y") or 0.0),
                width,
                height,
            ).normalized()

    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
''',
    )

    tests = Path("tests/test_graphics2_smart_slot_detection_manual.py")
    text = tests.read_text(encoding="utf-8")
    marker = "def test_strict_group_name_price_without_third_role_is_not_product():"
    if marker not in text:
        text += '''\n\ndef test_strict_group_name_price_without_third_role_is_not_product():
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
'''
        tests.write_text(text, encoding="utf-8")

    Path("tools/g2_apply_smart_slot_decorative_manual.py").unlink()


if __name__ == "__main__":
    main()
