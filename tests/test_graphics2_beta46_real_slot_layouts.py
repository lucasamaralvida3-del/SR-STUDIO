from __future__ import annotations

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import bind_product_to_item_slot, create_item_slot
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage, BindingRole
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.promotion_composition import apply_slot_composition
from srstudio.graphics2.promotion_layouts import plan_promotion


def make_session():
    document = GraphicsDocument(name="Real slot composition")
    document.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(document)


@pytest.mark.parametrize("mode,count", [("individual", 1), ("six", 6), ("seven", 7), ("eleven", 11), ("auto", 6)])
def test_every_promotion_position_uses_real_editable_slot(mode, count):
    session = make_session()
    router = ItemSlotCommandRouter(session)
    data = {"name": "apply_promotion_layout", "mode": mode, "reuse_existing": True}
    if mode == "auto":
        data["count"] = count
    result = router.dispatch(data)
    assert result.ok, result.message
    assert result.payload["component_source"] == "canonical-smart-slots"
    assert len(result.payload["slot_ids"]) == count
    assert set(result.payload["slot_ids"]) == set(result.payload["created_slot_ids"])
    assert not result.payload["reused_slot_ids"]
    assert len(session.page.slots) == count
    for sid in result.payload["slot_ids"]:
        slot = session.page.slots[sid]
        assert slot.metadata["source"] == "manual-item-slot"
        assert slot.metadata["preset_id"] in {"individual-beta44", "multi-cell-beta44"}
        assert BindingRole.IMAGE.value in slot.node_by_role
        assert BindingRole.PRICE_REAIS.value in slot.node_by_role
    assert session.page.metadata["promotion_composition"]["slot_ids"] == result.payload["slot_ids"]


def test_layout_reuses_existing_product_instead_of_making_a_blank_copy():
    session = make_session()
    original = create_item_slot(session, "individual-beta44", x=22, y=20)
    bind_product_to_item_slot(session, original.id, {
        "id": "SKU-998", "name": "Cafe Forte 500g", "price": "23,99", "club_price": "21,99"
    })
    before_page = session.page.id
    before_price = session.page.node(original.node_by_role[BindingRole.PRICE_REAIS.value]).text
    original_root = original.metadata["root_node_id"]
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout", "mode": "six",
        "price_mode": "auto", "reuse_existing": True,
    })
    assert result.ok
    assert session.page.id == before_page
    assert original.id in result.payload["reused_slot_ids"]
    assert original.id not in result.payload["created_slot_ids"]
    assert len(result.payload["created_slot_ids"]) == 5
    assert session.page.slots[original.id].product_id == "SKU-998"
    assert session.page.node(original.node_by_role[BindingRole.PRICE_REAIS.value]).text == before_price
    plan = plan_promotion("six")
    root = session.page.node(original_root).rect
    assert root.x == pytest.approx(plan.placements[0].x * session.page.width)
    assert root.width == pytest.approx(plan.placements[0].width * session.page.width)


def test_eleven_item_layout_reuses_the_actual_multi5_parent_with_saved_products():
    session = make_session()
    originals = []
    for i in range(6):
        slot = create_item_slot(session, "individual-beta44")
        bind_product_to_item_slot(session, slot.id, {
            "id": f"TOP-{i}", "name": f"Produto {i}", "price": f"{i+2},99"
        })
        originals.append(slot.id)
    multi = create_multi_item_strip(session, count=5, x=100, y=500)
    for index, sid in enumerate(multi["slot_ids"]):
        bind_product_to_item_slot(session, sid, {
            "id": f"BOTTOM-{index}", "name": f"Item {index}", "price": "9,99"
        })
    original_slots = set(session.page.slots)
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout", "mode": "eleven", "reuse_existing": True,
    })
    assert result.ok
    assert not result.payload["created_slot_ids"]
    assert set(result.payload["reused_slot_ids"]) == original_slots
    assert len(result.payload["slot_ids"]) == 11
    assert len(session.page.slots) == 11
    assert multi["root_node_id"] in result.payload["root_node_ids"]
    assert session.page.node(multi["root_node_id"]).metadata["multi_count"] == 5
    for index, sid in enumerate(multi["slot_ids"]):
        assert session.page.slots[sid].product_id == f"BOTTOM-{index}"


def test_eleven_filled_individual_cards_all_reused_without_new_multi():
    session = make_session()
    originals = []
    for index in range(11):
        slot = create_item_slot(session, "individual-beta44")
        assert bind_product_to_item_slot(session, slot.id, {
            "id": f"SKU-{index}", "name": f"Produto {index}", "price": "14,99",
        })
        originals.append(slot.id)
    old_page = session.page.id
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout", "mode": "eleven", "reuse_existing": True
    })
    assert result.ok
    assert result.payload["created_slot_ids"] == []
    assert set(result.payload["reused_slot_ids"]) == set(originals)
    assert session.page.id == old_page
    assert len(session.page.slots) == 11
    assert not any(node.metadata.get("multi_slot_beta44") for node in session.page.nodes.values())
    assert [session.page.slots[sid].product_id for sid in originals] == [
        f"SKU-{index}" for index in range(11)
    ]


@pytest.mark.parametrize("count", [5, 6])
def test_auto_layout_positions_preexisting_multi_strip_without_creating_cards(count):
    session = make_session()
    multi = create_multi_item_strip(session, count=count, x=27, y=125)
    for index, sid in enumerate(multi["slot_ids"]):
        bind_product_to_item_slot(session, sid, {
            "id": f"MULTI-{index}", "name": f"Produto {index}", "price": "14,99"
        })
    roots_before = set(session.page.nodes)
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout", "mode": "auto",
        "count": count, "reuse_existing": True, "logo_reserved": .3,
    })
    assert result.ok
    assert result.payload["created_slot_ids"] == []
    assert result.payload["reused_slot_ids"] == multi["slot_ids"]
    assert result.payload["root_node_ids"] == [multi["root_node_id"]]
    assert set(session.page.nodes) == roots_before
    group = session.page.node(multi["root_node_id"])
    assert group.rect.y >= session.page.height * .3
    assert group.rect.width / group.rect.height == pytest.approx(4, abs=.03)
    assert all(session.page.slots[sid].product_id == f"MULTI-{i}"
               for i, sid in enumerate(multi["slot_ids"]))


def test_existing_filled_product_is_selected_before_older_empty_slot():
    session = make_session()
    empty = create_item_slot(session, "individual-beta44")
    filled = create_item_slot(session, "individual-beta44")
    assert bind_product_to_item_slot(session, filled.id, {
        "id": "FILLED", "name": "Cafe 500 g", "price": "21,90"
    })
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout", "mode": "individual",
        "reuse_existing": True,
    })
    assert result.ok
    assert result.payload["slot_ids"] == [filled.id]
    assert result.payload["reused_slot_ids"] == [filled.id]
    assert empty.id in result.payload["unused_slot_ids"]
    assert session.page.slots[filled.id].product_id == "FILLED"


def test_insufficient_layout_capacity_rejected_without_moving_or_losing_products():
    session = make_session()
    router = ItemSlotCommandRouter(session)
    first = router.dispatch({
        "name": "apply_promotion_layout", "mode": "seven",
        "reuse_existing": True,
    })
    assert first.ok
    for i, sid in enumerate(first.payload["slot_ids"]):
        bind_product_to_item_slot(session, sid, {
            "id": f"PRODUCT-{i}", "name": f"Item {i}", "price": "12,59",
        })
    original = session.document.to_dict()
    result = router.dispatch({
        "name": "apply_promotion_layout", "mode": "six",
        "reuse_existing": True,
    })
    assert not result.ok
    assert "7 Smart Slots preenchidos" in result.message
    assert session.document.to_dict() == original


def test_empty_unused_slot_is_hidden_not_deleted_and_can_be_reused_later():
    session = make_session()
    first = create_item_slot(session, "individual-beta44")
    second = create_item_slot(session, "individual-beta44")
    router = ItemSlotCommandRouter(session)
    small = router.dispatch({"name": "apply_promotion_layout",
                             "mode": "individual", "reuse_existing": True})
    assert small.ok, small.message
    assert len(session.page.slots) == 2
    assert session.page.node(first.metadata["root_node_id"]).visible
    assert not session.page.node(second.metadata["root_node_id"]).visible
    large = router.dispatch({"name": "apply_promotion_layout",
                             "mode": "six", "reuse_existing": True})
    assert large.ok
    assert second.id in large.payload["reused_slot_ids"]
    assert session.page.node(second.metadata["root_node_id"]).visible
    assert len(session.page.slots) == 6


def test_filled_multi_cannot_be_silently_split_by_incompatible_layout():
    session = make_session()
    multi = create_multi_item_strip(session, count=5)
    for i, sid in enumerate(multi["slot_ids"]):
        bind_product_to_item_slot(session, sid, {
            "id": f"SKU-{i}", "name": f"Produto {i}", "price": "7,99"
        })
    original = session.document.to_dict()
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout",
        "mode": "six", "reuse_existing": True,
    })
    assert not result.ok
    assert "faixa Multi preenchida" in result.message
    assert session.document.to_dict() == original


def test_reorganizing_slots_changes_positions_not_visual_preset_styles():
    session = make_session()
    individual = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, individual.id, {
        "id": "A1", "name": "CAFÉ TRADICIONAL 500 G", "price": "19,90"
    })
    root_id = individual.metadata["root_node_id"]
    page = session.page
    import copy
    child_styles = {
        node_id: copy.deepcopy(page.node(node_id).style)
        for node_id in [root_id, *page.descendants(root_id)]
    }
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout", "mode": "six", "reuse_existing": True
    })
    assert result.ok
    assert individual.id in result.payload["reused_slot_ids"]
    for node_id, expected_style in child_styles.items():
        assert page.node(node_id).style == expected_style
    assert page.slots[individual.id].product_id == "A1"


def test_auto_layout_24_products_does_not_drop_ids_or_leave_logo_region():
    session = make_session()
    original = []
    for index in range(24):
        slot = create_item_slot(session, "individual-beta44")
        bind_product_to_item_slot(session, slot.id, {
            "id": f"SKU-{index:02d}",
            "name": f"PRODUTO DE MERCEARIA TIPO {index + 1} 500 GRAMAS",
            "price": f"{index + 2},99",
        })
        original.append(slot.id)
    result = ItemSlotCommandRouter(session).dispatch({
        "name": "apply_promotion_layout", "mode": "auto",
        "count": 24, "logo_reserved": .3,
        "reuse_existing": True,
    })
    assert result.ok
    assert set(result.payload["reused_slot_ids"]) == set(original)
    assert not result.payload["created_slot_ids"]
    assert session.page.metadata["promotion_composition"]["slot_ids"] == result.payload["slot_ids"]
    rectangles = []
    for slot_id in result.payload["slot_ids"]:
        slot = session.page.slots[slot_id]
        assert slot.product_id in {f"SKU-{i:02d}" for i in range(24)}
        root = session.page.node(slot.metadata["root_node_id"]).rect.normalized()
        assert root.y >= .3 * session.page.height
        assert root.right <= session.page.width + .01
        assert root.bottom <= session.page.height + .01
        rectangles.append(root)
    for index, a in enumerate(rectangles):
        for b in rectangles[index+1:]:
            assert not (a.x < b.right-.01 and b.x < a.right-.01
                        and a.y < b.bottom-.01 and b.y < a.bottom-.01)


def test_contents_remain_editable_and_text_fit_contract_survives_shrinking():
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    assert bind_product_to_item_slot(session, slot.id, {
        "id": "LONG",
        "name": "CAFE TORRADO MOIDO EXTRAFORTE EMBALAGEM ECONOMICA 500G",
        "price": "1299,99", "unit": "UN",
    })
    page = session.page
    roles = (BindingRole.NAME, BindingRole.PRICE_REAIS,
             BindingRole.PRICE_CENTS, BindingRole.CURRENCY, BindingRole.UNIT)
    original_content = {role.value: page.node(slot.node_by_role[role.value]).text
                        for role in roles}
    root_id = slot.metadata["root_node_id"]
    root = page.node(root_id)
    initial = root.rect.normalized()
    session.resize_node(
        root_id, x=75, y=350,
        width=initial.width * .38,
        height=initial.height * .38,
    )
    for role in roles:
        node = page.node(slot.node_by_role[role.value])
        assert node.text == original_content[role.value]
        assert node.style["fit_inside_box"] is True
        assert node.style["min_font_size"] >= 7
        assert node.rect.width > 0 and node.rect.height > 0
    assert session.undo()
    assert page.slots[slot.id].product_id == "LONG"


def test_second_layout_application_does_not_duplicate_images_or_slot_ids():
    session = make_session()
    router = ItemSlotCommandRouter(session)
    first = router.dispatch({"name": "apply_promotion_layout", "mode": "six"})
    assert first.ok
    before = set(session.page.slots)
    second = router.dispatch({"name": "apply_promotion_layout", "mode": "six"})
    assert second.ok
    assert set(session.page.slots) == before
    assert set(second.payload["reused_slot_ids"]) == before
    assert not second.payload["created_slot_ids"]
    restored = GraphicsDocument.from_dict(session.document.to_dict())
    assert set(restored.active_page.slots) == before


def test_reuse_existing_false_creates_separate_slots_without_erasing_originals():
    session = make_session()
    original = create_item_slot(session, "individual-beta44")
    result = apply_slot_composition(session, plan_promotion("individual"), reuse_existing=False)
    assert original.id not in result.slot_ids
    assert original.id in result.unused_slot_ids
    assert original.id in session.page.slots
    assert len(session.page.slots) == 2


def test_preview_catalog_uses_runtime_rendered_real_slot_and_layout_pngs(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtCore import QUrl
    from srstudio.graphics2.slot_preview import PREVIEW_TYPES, build_slot_preview_catalog

    app = QGuiApplication.instance() or QGuiApplication([])
    catalog = build_slot_preview_catalog(tmp_path)
    assert set(catalog) == set(PREVIEW_TYPES)
    for key, url in catalog.items():
        file = QUrl(url).toLocalFile()
        image = QImage(file)
        assert not image.isNull(), key
        assert image.width() > 40 and image.height() > 35, key
    multi = QImage(QUrl(catalog["multi5"]).toLocalFile())
    individual = QImage(QUrl(catalog["individual"]).toLocalFile())
    assert multi.width() > multi.height() * 3
    assert individual.height() > individual.width()
    for key in ("layout-six", "layout-seven", "layout-eleven"):
        preview = QImage(QUrl(catalog[key]).toLocalFile())
        assert preview.height() > preview.width()
    # The previews are not static QML illustrations. Selecting two prices
    # must result in visibly different pixels rendered by the real slot.
    for key in ("individual", "multi5", "multi6"):
        one = QImage(QUrl(catalog[key]).toLocalFile())
        two = QImage(QUrl(catalog[key + "-two"]).toLocalFile())
        assert one.size() == two.size()
        assert any(
            one.pixel(x, y) != two.pixel(x, y)
            for y in range(0, one.height(), 2)
            for x in range(0, one.width(), 2)
        ), f"Two-price preview {key} did not change the actual visual component"

