from __future__ import annotations

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsSession, build_semantic_blocks


def test_description_and_validity_remain_productcard_members_after_rebuilds():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch(
        {
            "name": "create_product_card",
            "include_description": True,
            "include_validity": True,
            "include_image": False,
        }
    )
    assert created.ok and created.changed
    slot_id = str(created.payload["slot_id"])

    bound = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot_id,
            "product": {
                "id": "aux-1",
                "display_name": "CAFÉ 500G",
                "description": "TORRA MÉDIA",
                "price": "19,90",
                "unit": "UN",
                "validity": "20/08/2026",
            },
        }
    )
    assert bound.ok and bound.changed

    slot = session.page.slots[slot_id]
    description_id = slot.node_by_role["description"]
    validity_id = slot.node_by_role["validity"]

    for _ in range(3):
        build_semantic_blocks(session.document)
        slot = session.page.slots[slot_id]
        card_id = str(slot.metadata["semantic_product_card_id"])
        card = session.page.metadata["semantic_blocks"][card_id]
        assert description_id in card["members"]
        assert validity_id in card["members"]
        assert session.page.node(description_id).metadata["semantic_product_card_id"] == card_id
        assert session.page.node(validity_id).metadata["semantic_product_card_id"] == card_id
        assert session.page.node(description_id).text == "TORRA MÉDIA"
        assert session.page.node(validity_id).text == "20/08/2026"


def test_metadata_description_binding_survives_dynamic_update_and_rebuild():
    session = GraphicsSession()
    router = GraphicsCommandRouter(session)
    created = router.dispatch(
        {
            "name": "create_product_card",
            "include_description": True,
            "include_image": False,
        }
    )
    slot_id = str(created.payload["slot_id"])
    assert router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot_id,
            "product": {
                "id": "aux-2",
                "display_name": "ARROZ 5KG",
                "price": "24,90",
                "metadata": {"description": "TIPO 1"},
            },
        }
    ).changed

    slot = session.page.slots[slot_id]
    description = session.page.node(slot.node_by_role["description"])
    assert description.text == "TIPO 1"

    updated = router.dispatch(
        {
            "name": "update_product_fields",
            "slot_id": slot_id,
            "changes": {"metadata": {"description": "TIPO 1 PREMIUM"}},
        }
    )
    assert updated.ok and updated.changed
    assert description.text == "TIPO 1 PREMIUM"

    build_semantic_blocks(session.document)
    slot = session.page.slots[slot_id]
    card = session.page.metadata["semantic_blocks"][slot.metadata["semantic_product_card_id"]]
    assert description.id in card["members"]
    assert description.text == "TIPO 1 PREMIUM"
