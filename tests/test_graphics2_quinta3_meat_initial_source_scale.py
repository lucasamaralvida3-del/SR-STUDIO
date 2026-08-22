from __future__ import annotations

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage, Rect
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.slot_corpus_families import QUINTA3_FAMILY_PRESETS
from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID, MEAT_STRIP_FULL_CARD_PROFILES
from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER, strip_ownership_snapshot
from srstudio.graphics2.slot_corpus_meat_strip_source_contract import (
    SOURCE_FILE,
    SOURCE_PAGE_HEIGHT_EMU,
    SOURCE_PAGE_WIDTH_EMU,
    SOURCE_SHA256,
)


PRODUCTS = {
    "costela": {"id": "prod-costela", "name": "COSTELA GAÚCHA", "price": "24.79", "unit": "KG"},
    "pernil": {"id": "prod-pernil", "name": "PERNIL SUÍNO S/ OSSO", "price": "19.99", "unit": "KG"},
    "musculo": {"id": "prod-musculo", "name": "MÚSCULO BOVINO", "price": "26.90", "unit": "KG"},
    "moela": {"id": "prod-moela", "name": "MOELA DE FRANGO", "price": "12.49", "unit": "KG"},
}

# Test-only oracles derived independently from the exact PPTX p:sldSz.  Runtime
# code must derive these values from source EMUs and never hardcode them.
CELL_SIZE_ORACLES = {
    "costela": (160.00902887139108, 133.1004792879151),
    "pernil": (140.16692913385828, 133.2800955463571),
    "musculo": (140.1818372703412, 131.73802169244655),
    "moela": (139.3312335958005, 133.1004792879151),
}
SOURCE_STRIP_SIZE_ORACLE = (579.6890288713911, 133.2800955463571)


def _session() -> GraphicsSession:
    document = GraphicsDocument(name="Quinta3 Meat initial source scale")
    document.pages = [GraphicsPage(name="Página 1", width=1080.0, height=1350.0, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    return GraphicsSession(document)


def _source_strip() -> Rect:
    roots = [MEAT_STRIP_FULL_CARD_PROFILES[profile]["root_emu"] for profile in PROFILE_ORDER]
    left = min(float(root[0]) for root in roots)
    top = min(float(root[1]) for root in roots)
    right = max(float(root[0]) + float(root[2]) for root in roots)
    bottom = max(float(root[1]) + float(root[3]) for root in roots)
    return Rect(left, top, right - left, bottom - top)


def _add_bound(router: ItemSlotCommandRouter, session: GraphicsSession, profile_id: str):
    result = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
    assert result.ok and result.changed, result.to_dict()
    slot = session.page.slots[result.payload["slot_id"]]
    assert slot.metadata["full_card_profile"] == profile_id
    product = dict(PRODUCTS[profile_id])
    product["quinta3_supervised_profile"] = profile_id
    bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
    assert bound.ok and bound.changed, bound.to_dict()
    return slot


def _four_bound_cells():
    session = _session()
    router = ItemSlotCommandRouter(session)
    slots = [_add_bound(router, session, profile_id) for profile_id in PROFILE_ORDER]
    return session, slots


def _inside(page, rect: Rect) -> bool:
    rect = rect.normalized()
    return (
        rect.x >= -1e-6
        and rect.y >= -1e-6
        and rect.right <= float(page.width) + 1e-6
        and rect.bottom <= float(page.height) + 1e-6
    )


def test_exact_pptx_source_page_contract_is_frozen_with_source_identity() -> None:
    assert SOURCE_FILE == "OFERTAS QUINTA FILÉ NOVO (3).pptx"
    assert SOURCE_SHA256 == "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
    assert SOURCE_PAGE_WIDTH_EMU == 10287000.0
    assert SOURCE_PAGE_HEIGHT_EMU == 12852400.0


def test_initial_source_scale_uses_exact_pptx_page_mapping_not_generic_preset() -> None:
    session = _session()
    router = ItemSlotCommandRouter(session)
    first = _add_bound(router, session, "costela")
    strip = session.page.node(str(first.metadata["meat_strip_root_id"]))
    assert strip is not None

    source_strip = _source_strip()
    expected_scale_x = session.page.width / SOURCE_PAGE_WIDTH_EMU
    expected_scale_y = session.page.height / SOURCE_PAGE_HEIGHT_EMU
    expected_width = source_strip.width * expected_scale_x
    expected_height = source_strip.height * expected_scale_y
    actual = strip.rect.normalized()

    assert expected_width == pytest.approx(SOURCE_STRIP_SIZE_ORACLE[0])
    assert expected_height == pytest.approx(SOURCE_STRIP_SIZE_ORACLE[1])
    assert actual.width == pytest.approx(expected_width)
    assert actual.height == pytest.approx(expected_height)
    assert actual.width / expected_width == pytest.approx(1.0)
    assert actual.height / expected_height == pytest.approx(1.0)
    assert strip.metadata["source_page_emu"] == [SOURCE_PAGE_WIDTH_EMU, SOURCE_PAGE_HEIGHT_EMU]
    assert strip.metadata["initial_scale_source"] == "source-page-to-runtime-page"

    # Regression for the older implementation: the source page mapping must
    # never be inferred from generic ProductCell preset dimensions.
    preset = QUINTA3_FAMILY_PRESETS[MEAT_FAMILY_ID]
    source_costela = MEAT_STRIP_FULL_CARD_PROFILES["costela"]["root_emu"]
    legacy_scale_x = float(preset["width"]) / float(source_costela[2])
    legacy_scale_y = float(preset["height"]) / float(source_costela[3])
    assert actual.width != pytest.approx(source_strip.width * legacy_scale_x)
    assert actual.height != pytest.approx(source_strip.height * legacy_scale_y)


def test_initial_four_cells_exact_sizes_curve_right_and_separator_three_are_in_bounds() -> None:
    session, slots = _four_bound_cells()
    page = session.page
    strip_id = str(slots[0].metadata["meat_strip_root_id"])
    strip = page.node(strip_id)
    assert strip is not None
    assert _inside(page, strip.rect)
    assert strip.rect.normalized().right == pytest.approx(354.0 + SOURCE_STRIP_SIZE_ORACLE[0])

    for profile_id, slot in zip(PROFILE_ORDER, slots):
        root = page.node(str(slot.metadata["root_node_id"]))
        assert root is not None, profile_id
        assert _inside(page, root.rect), (profile_id, root.rect)
        source = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]["root_emu"]
        expected_width = float(source[2]) / SOURCE_PAGE_WIDTH_EMU * float(page.width)
        expected_height = float(source[3]) / SOURCE_PAGE_HEIGHT_EMU * float(page.height)
        oracle_width, oracle_height = CELL_SIZE_ORACLES[profile_id]
        assert expected_width == pytest.approx(oracle_width)
        assert expected_height == pytest.approx(oracle_height)
        actual = root.rect.normalized()
        assert actual.width == pytest.approx(expected_width)
        assert actual.height == pytest.approx(expected_height)

    snapshot = strip_ownership_snapshot(page, strip_id)
    assert len(snapshot["cell_slot_ids"]) == 4
    assert len(snapshot["cell_root_ids"]) == 4
    assert set(snapshot["cell_slot_ids"]) == {slot.id for slot in slots}
    for slot in slots:
        root = page.node(str(slot.metadata["root_node_id"]))
        assert root is not None
        assert root.parent_id == strip_id

    shared = [page.node(node_id) for node_id in snapshot["shared_visual_nodes"]]
    shared = [node for node in shared if node is not None]

    # Freeform 3 owns both strip curves. If its complete source-derived runtime
    # rect is in page bounds, the right curve is not clipped at the page edge.
    curve = next(node for node in shared if str(node.metadata.get("source_shape_id") or "") == "3")
    assert _inside(page, curve.rect)

    # AutoShape 7 is the third/right-most separator in the supervised strip.
    separator_three = next(node for node in shared if str(node.metadata.get("source_shape_id") or "") == "7")
    assert _inside(page, separator_three.rect)


def test_strip_ownership_move_and_resize_still_propagate_to_product_cells() -> None:
    session, slots = _four_bound_cells()
    page = session.page
    strip_id = str(slots[0].metadata["meat_strip_root_id"])
    strip = page.node(strip_id)
    assert strip is not None

    cell_roots = [page.node(str(slot.metadata["root_node_id"])) for slot in slots]
    assert all(root is not None for root in cell_roots)
    before_move = {root.id: root.rect.normalized() for root in cell_roots if root is not None}

    session.select(strip_id)
    session.move_selected(9.0, 7.0)
    moved_strip = page.node(strip_id)
    assert moved_strip is not None
    for root in cell_roots:
        assert root is not None
        before = before_move[root.id]
        after = page.node(root.id).rect.normalized()
        assert (after.x, after.y, after.width, after.height) == pytest.approx(
            (before.x + 9.0, before.y + 7.0, before.width, before.height)
        )

    before_resize = {root.id: page.node(root.id).rect.normalized() for root in cell_roots if root is not None}
    old_strip = moved_strip.rect.normalized()
    session.resize_node(
        strip_id,
        x=old_strip.x,
        y=old_strip.y,
        width=old_strip.width * 0.96,
        height=old_strip.height * 1.04,
    )
    resized_strip = page.node(strip_id).rect.normalized()
    assert resized_strip.width == pytest.approx(old_strip.width * 0.96)
    assert resized_strip.height == pytest.approx(old_strip.height * 1.04)
    for root in cell_roots:
        assert root is not None
        before = before_resize[root.id]
        after = page.node(root.id).rect.normalized()
        assert after.width == pytest.approx(before.width * 0.96)
        assert after.height == pytest.approx(before.height * 1.04)


def test_manual_strip_resize_remains_authoritative_across_more_cells_and_reopen(tmp_path) -> None:
    session = _session()
    router = ItemSlotCommandRouter(session)
    first = _add_bound(router, session, "costela")
    strip_id = str(first.metadata["meat_strip_root_id"])
    strip = session.page.node(strip_id)
    assert strip is not None
    initial = strip.rect.normalized()

    edited = Rect(
        initial.x + 11.0,
        initial.y + 7.0,
        initial.width * 0.88,
        initial.height * 1.06,
    )
    session.resize_node(
        strip_id,
        x=edited.x,
        y=edited.y,
        width=edited.width,
        height=edited.height,
    )
    after_edit = session.page.node(strip_id).rect.normalized()

    # Adding the remaining supervised cells must reuse the edited root, not
    # re-run source-page initial normalization.
    for profile_id in PROFILE_ORDER[1:]:
        _add_bound(router, session, profile_id)
    after_four = session.page.node(strip_id).rect.normalized()
    assert (after_four.x, after_four.y, after_four.width, after_four.height) == pytest.approx(
        (after_edit.x, after_edit.y, after_edit.width, after_edit.height)
    )

    snapshot = strip_ownership_snapshot(session.page, strip_id)
    assert len(snapshot["cell_slot_ids"]) == 4
    assert len(snapshot["cell_root_ids"]) == 4

    output = tmp_path / "quinta3-meat-strip-resized.srscene"
    save_package(session.document, output, embed_local_assets=False)
    reopened = load_package(output)
    restored = reopened.active_page.node(strip_id)
    assert restored is not None
    restored_rect = restored.rect.normalized()
    assert (restored_rect.x, restored_rect.y, restored_rect.width, restored_rect.height) == pytest.approx(
        (after_edit.x, after_edit.y, after_edit.width, after_edit.height)
    )
    assert len(reopened.active_page.slots) == 4
    restored_snapshot = strip_ownership_snapshot(reopened.active_page, strip_id)
    assert len(restored_snapshot["cell_slot_ids"]) == 4
    assert len(restored_snapshot["cell_root_ids"]) == 4
