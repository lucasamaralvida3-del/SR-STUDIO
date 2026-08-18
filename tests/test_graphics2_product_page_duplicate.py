from __future__ import annotations

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsSession
from srstudio.graphics2.preflight import run_preflight


def _all_bound_ids(slot) -> set[str]:
    ids = {str(node_id) for node_id in slot.node_by_role.values() if str(node_id)}
    for raw in dict(slot.metadata.get("extra_bindings") or {}).values():
        if isinstance(raw, str):
            ids.add(raw)
        else:
            ids.update(str(node_id) for node_id in raw if str(node_id))
    return ids


def test_duplicate_page_remaps_full_productcard_bindings_and_keeps_snapshot_independent():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch(
        {
            "name": "create_product_card",
            "include_image": True,
            "include_description": True,
            "include_quantity": True,
            "include_validity": True,
            "include_app_price": True,
            "include_wholesale": True,
        }
    )
    source_page = session.page
    source_slot_id = str(created.payload["slot_id"])
    product = {
        "id": "dup-1",
        "display_name": "CAFÉ 500G",
        "description": "TORRA MÉDIA",
        "price": "19,90",
        "app_price": "17,90",
        "wholesale_price": "16,90",
        "quantity": "6",
        "unit": "UN",
        "validity": "20/08/2026",
        "image_path": "cafe-dup.png",
    }
    assert router.dispatch(
        {"name": "bind_product", "slot_id": source_slot_id, "product": product}
    ).changed

    source_slot = source_page.slots[source_slot_id]
    source_bound_ids = _all_bound_ids(source_slot)
    source_snapshot = source_slot.metadata["product_snapshot"]

    duplicate_page_id = session.add_page(duplicate_active=True)
    duplicate_page = session.page
    duplicate_slot = next(iter(duplicate_page.slots.values()))
    duplicate_bound_ids = _all_bound_ids(duplicate_slot)

    assert duplicate_page.id == duplicate_page_id
    assert duplicate_slot.id != source_slot.id
    assert duplicate_slot.page_id == duplicate_page.id
    assert duplicate_bound_ids
    assert duplicate_bound_ids.isdisjoint(source_bound_ids)
    assert duplicate_bound_ids.issubset(set(duplicate_page.nodes))
    assert duplicate_slot.product_id == "dup-1"
    assert duplicate_slot.metadata["product_snapshot"] == source_snapshot
    assert duplicate_slot.metadata["product_snapshot"] is not source_snapshot

    for role, raw_ids in dict(duplicate_slot.metadata.get("extra_bindings") or {}).items():
        ids = [raw_ids] if isinstance(raw_ids, str) else list(raw_ids)
        assert ids, role
        assert set(ids).issubset(set(duplicate_page.nodes))
        assert set(ids).isdisjoint(source_bound_ids)

    duplicate_router = GraphicsCommandRouter(session)
    edited = duplicate_router.dispatch(
        {
            "name": "update_product_fields",
            "slot_id": duplicate_slot.id,
            "changes": {"display_name": "CAFÉ SOMENTE CÓPIA", "price": "18,49"},
        }
    )
    assert edited.ok and edited.changed
    duplicate_name = duplicate_page.node(duplicate_slot.node_by_role["name"])
    source_name = source_page.node(source_slot.node_by_role["name"])
    assert duplicate_name.text == "CAFÉ SOMENTE CÓPIA"
    assert source_name.text == "CAFÉ 500G"
    assert duplicate_slot.metadata["product_snapshot"]["display_name"] == "CAFÉ SOMENTE CÓPIA"
    assert source_slot.metadata["product_snapshot"]["display_name"] == "CAFÉ 500G"

    assert not [issue for issue in run_preflight(session.document) if issue.severity == "error"]
