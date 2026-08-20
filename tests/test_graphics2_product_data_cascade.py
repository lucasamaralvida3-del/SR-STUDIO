from __future__ import annotations

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsSession


def _page(session: GraphicsSession, page_id: str):
    return next(page for page in session.document.pages if page.id == page_id)


def _slot_name(page, slot_id: str) -> str:
    slot = page.slots[slot_id]
    return page.node(slot.node_by_role["name"]).text


def _slot_price(page, slot_id: str) -> str:
    slot = page.slots[slot_id]
    return page.node(slot.node_by_role["price_complete"]).text


def _slot_quantity(page, slot_id: str) -> str:
    slot = page.slots[slot_id]
    return page.node(slot.node_by_role["quantity"]).text


def _build_two_page_same_product_session() -> tuple[GraphicsSession, str, str, str, str]:
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    product = {
        "id": "p1",
        "display_name": "CAFÉ 500G",
        "price": "19,90",
        "quantity": "3",
        "unit": "UN",
    }
    session.document.metadata["products"] = [dict(product)]

    page_a = session.page.id
    created_a = router.dispatch({"name": "create_product_card", "include_quantity": True})
    slot_a = str(created_a.payload["slot_id"])
    assert router.dispatch({"name": "bind_product", "slot_id": slot_a, "product": product}).ok

    page_b = session.add_page(name="Página 2")
    created_b = router.dispatch({"name": "create_product_card", "include_quantity": True})
    slot_b = str(created_b.payload["slot_id"])
    assert router.dispatch({"name": "bind_product", "slot_id": slot_b, "product": product}).ok
    return session, page_a, slot_a, page_b, slot_b


def test_update_product_data_cascades_across_pages_in_one_undoable_transaction():
    session, page_a, slot_a, page_b, slot_b = _build_two_page_same_product_session()
    router = GraphicsCommandRouter(session)
    active_before = session.document.active_page_id

    result = router.dispatch(
        {
            "name": "update_product_data",
            "product_id": "p1",
            "changes": {
                "display_name": "CAFÉ PREMIUM 500G",
                "price": "21,49",
                "quantity": "6",
            },
        }
    )

    assert result.ok and result.changed
    assert result.payload["slots_updated"] == 2
    assert result.payload["slots_skipped_locked"] == 0
    assert result.payload["catalog_updated"] is True
    assert set(result.payload["page_ids"]) == {page_a, page_b}
    assert session.document.active_page_id == active_before
    assert session.document.metadata["products"][0]["display_name"] == "CAFÉ PREMIUM 500G"
    assert session.document.metadata["products"][0]["price"] == "21,49"
    assert _slot_name(_page(session, page_a), slot_a) == "CAFÉ PREMIUM 500G"
    assert _slot_name(_page(session, page_b), slot_b) == "CAFÉ PREMIUM 500G"
    assert _slot_price(_page(session, page_a), slot_a) == "21,49"
    assert _slot_price(_page(session, page_b), slot_b) == "21,49"
    assert _slot_quantity(_page(session, page_a), slot_a) == "6"
    assert _slot_quantity(_page(session, page_b), slot_b) == "6"

    assert session.undo() is True
    assert session.document.metadata["products"][0]["display_name"] == "CAFÉ 500G"
    assert _slot_name(_page(session, page_a), slot_a) == "CAFÉ 500G"
    assert _slot_name(_page(session, page_b), slot_b) == "CAFÉ 500G"
    assert _slot_price(_page(session, page_a), slot_a) == "19,90"
    assert _slot_quantity(_page(session, page_b), slot_b) == "3"

    assert session.redo() is True
    assert session.document.metadata["products"][0]["price"] == "21,49"
    assert _slot_price(_page(session, page_a), slot_a) == "21,49"
    assert _slot_price(_page(session, page_b), slot_b) == "21,49"


def test_update_product_fields_changes_only_selected_card_snapshot():
    session, page_a, slot_a, page_b, slot_b = _build_two_page_same_product_session()
    # Active page is page B.
    router = GraphicsCommandRouter(session)

    result = router.dispatch(
        {
            "name": "update_product_fields",
            "slot_id": slot_b,
            "changes": {"display_name": "CAFÉ DESTAQUE LOCAL", "price": "18,99", "quantity": "2"},
        }
    )

    assert result.ok and result.changed
    assert result.payload["slots_updated"] == 1
    assert _slot_name(_page(session, page_b), slot_b) == "CAFÉ DESTAQUE LOCAL"
    assert _slot_price(_page(session, page_b), slot_b) == "18,99"
    assert _slot_quantity(_page(session, page_b), slot_b) == "2"
    assert _slot_name(_page(session, page_a), slot_a) == "CAFÉ 500G"
    assert _slot_price(_page(session, page_a), slot_a) == "19,90"
    assert session.document.metadata["products"][0]["display_name"] == "CAFÉ 500G"
    assert _page(session, page_b).slots[slot_b].metadata["product_snapshot"]["display_name"] == "CAFÉ DESTAQUE LOCAL"


def test_cascade_reports_locked_slots_and_preserves_their_visual_snapshot():
    session, page_a, slot_a, page_b, slot_b = _build_two_page_same_product_session()
    router = GraphicsCommandRouter(session)
    _page(session, page_a).slots[slot_a].locked = True

    result = router.dispatch(
        {
            "name": "update_product_data",
            "product_id": "p1",
            "changes": {"price": "22,90", "quantity": "12"},
        }
    )

    assert result.ok and result.changed
    assert result.payload["slots_updated"] == 1
    assert result.payload["slots_skipped_locked"] == 1
    assert result.payload["catalog_updated"] is True
    assert _slot_price(_page(session, page_a), slot_a) == "19,90"
    assert _slot_quantity(_page(session, page_a), slot_a) == "3"
    assert _slot_price(_page(session, page_b), slot_b) == "22,90"
    assert _slot_quantity(_page(session, page_b), slot_b) == "12"


def test_cascade_noop_does_not_create_history_entry_or_report_changes():
    session, page_a, slot_a, page_b, slot_b = _build_two_page_same_product_session()
    router = GraphicsCommandRouter(session)
    # Consume existing history so the label check is deterministic by first
    # creating a real cascade and then issuing the exact same values.
    first = router.dispatch(
        {"name": "update_product_data", "product_id": "p1", "changes": {"price": "20,49"}}
    )
    assert first.changed
    undo_label = session.history.undo_label

    second = router.dispatch(
        {"name": "update_product_data", "product_id": "p1", "changes": {"price": "20,49"}}
    )

    assert second.ok and second.changed is False
    assert second.payload["slots_updated"] == 0
    assert second.payload["catalog_updated"] is False
    assert session.history.undo_label == undo_label
    assert _slot_price(_page(session, page_a), slot_a) == "20,49"
    assert _slot_price(_page(session, page_b), slot_b) == "20,49"
