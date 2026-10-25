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

