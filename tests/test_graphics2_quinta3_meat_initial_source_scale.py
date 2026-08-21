from __future__ import annotations

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage, Rect
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.slot_corpus_families import QUINTA3_FAMILY_PRESETS
from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID, MEAT_STRIP_FULL_CARD_PROFILES
from srstudio.graphics2.slot_corpus_meat_strip_ownership import (
    MEAT_STRIP_SOURCE_PAGE_HEIGHT_EMU,
    MEAT_STRIP_SOURCE_PAGE_WIDTH_EMU,
    PROFILE_ORDER,
    strip_ownership_snapshot,
)


PRODUCTS = {
    "costela": {"id": "prod-costela", "name": "COSTELA GAÚCHA", "price": "24.79", "unit": "KG"},
    "pernil": {"id": "prod-pernil", "name": "PERNIL SUÍNO S/ OSSO", "price": "19.99", "unit": "KG"},
    "musculo": {"id": "prod-musculo", "name": "MÚSCULO BOVINO", "price": "26.90", "unit": "KG"},
    "moela": {"id": "prod-moela", "name": "MOELA DE FRANGO", "price": "12.49", "unit": "KG"},
}


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


def test_initial_source_scale_uses_pptx_page_mapping_not_generic_preset() -> None:
    session = _session()
    router = ItemSlotCommandRouter(session)
    first = _add_bound(router, session, "costela")
    strip = session.page.node(str(first.metadata["meat_strip_root_id"]))
    assert strip is not None

    source_strip = _source_strip()
    expected_scale_x = session.page.width / MEAT_STRIP_SOURCE_PAGE_WIDTH_EMU
    expected_scale_y = session.page.height / MEAT_STRIP_SOURCE_PAGE_HEIGHT_EMU
    actual = strip.rect.normalized()

    assert actual.width == pytest.approx(source_strip.width * expected_scale_x)
    assert actual.height == pytest.approx(source_strip.height * expected_scale_y)
    assert strip.metadata["source_page_emu"] == [
        MEAT_STRIP_SOURCE_PAGE_WIDTH_EMU,
        MEAT_STRIP_SOURCE_PAGE_HEIGHT_EMU,
    ]
    assert strip.metadata["initial_scale_source"] == "source-page-to-runtime-page"

    # Regression for the P1: the old implementation scaled the whole source
    # strip from the generic first ProductCell preset width/height.
    preset = QUINTA3_FAMILY_PRESETS[MEAT_FAMILY_ID]
    source_costela = MEAT_STRIP_FULL_CARD_PROFILES["costela"]["root_emu"]
    legacy_scale_x = float(preset["width"]) / float(source_costela[2])
    legacy_scale_y = float(preset["height"]) / float(source_costela[3])
    assert actual.width != pytest.approx(source_strip.width * legacy_scale_x)
    assert actual.height != pytest.approx(source_strip.height * legacy_scale_y)


def test_initial_four_cells_curve_right_and_separator_three_are_in_bounds() -> None:
    session, slots = _four_bound_cells()
    page = session.page
    strip_id = str(slots[0].metadata["meat_strip_root_id"])
    strip = page.node(strip_id)
    assert strip is not None
    assert _inside(page, strip.rect)

    for profile_id, slot in zip(PROFILE_ORDER, slots):
        root = page.node(str(slot.metadata["root_node_id"]))
        assert root is not None, profile_id
        assert _inside(page, root.rect), (profile_id, root.rect)

    snapshot = strip_ownership_snapshot(page, strip_id)
    shared = [page.node(node_id) for node_id in snapshot["shared_visual_nodes"]]
    shared = [node for node in shared if node is not None]

    # Freeform 3 owns both strip curves. If its full runtime rect is inside the
    # page, the right curve cannot be clipped by the page edge.
    curve = next(node for node in shared if str(node.metadata.get("source_shape_id") or "") == "3")
    assert _inside(page, curve.rect)

    # AutoShape 7 is the third/right-most separator in the supervised strip.
    separator_three = next(node for node in shared if str(node.metadata.get("source_shape_id") or "") == "7")
    assert _inside(page, separator_three.rect)


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
