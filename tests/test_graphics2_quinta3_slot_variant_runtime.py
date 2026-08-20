from __future__ import annotations

import pytest

from srstudio.graphics2.item_slots import item_slot_snapshot
from srstudio.graphics2.model import BindingRole, GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks, semantic_block
from srstudio.graphics2.slot_corpus_variant_runtime import create_quinta3_item_slot


def test_club_promo_variant_materializes_secondary_split_price_and_independent_labels() -> None:
    session = GraphicsSession(GraphicsDocument(name="Quinta 3 variants"))

    slot = create_quinta3_item_slot(
        session,
        "quinta3-club-side",
        variant="club-promo",
        x=40,
        y=60,
    )

    extras = slot.metadata["extra_bindings"]
    assert set(extras) >= {
        "app_price_currency",
        "app_price_integer",
        "app_price_cents",
        "app_unit",
        "promotion",
        "club_label",
    }
    assert slot.metadata["promotion_visible"] is True
    assert slot.metadata["club_visible"] is True
    assert slot.metadata["secondary_price_visible"] is True
    assert session.page.node(slot.node_by_role[BindingRole.NAME.value]).text == "NOME DO PRODUTO"
    assert session.page.node(extras["promotion"][0]).text == "PROMOÇÃO"
    assert session.page.node(extras["club_label"][0]).text == "NO SR CLUBE SMART"

    report = build_semantic_blocks(session.document)
    assert report.price_blocks == 1
    assert report.app_price_blocks == 1
    app_block = semantic_block(session.page, f"priceblock:{slot.id}:app-price")
    assert app_block is not None
    assert app_block["metadata"]["split_complete"] is True
    assert set(app_block["roles"]) == {"currency", "reais", "cents", "unit"}


def test_compact_blue_and_beige_share_preset_but_apply_different_geometry() -> None:
    session = GraphicsSession(GraphicsDocument(name="Compact variants"))
    blue = create_quinta3_item_slot(session, "quinta3-compact-promo", variant="blue", x=20, y=30)
    blue_snapshot = item_slot_snapshot(session.page, blue)
    beige = create_quinta3_item_slot(session, "quinta3-compact-promo", variant="beige", x=420, y=30)
    beige_snapshot = item_slot_snapshot(session.page, beige)

    assert blue.metadata["preset_id"] == beige.metadata["preset_id"] == "quinta3-compact-promo"
    assert blue.metadata["quinta3_variant"] == "blue"
    assert beige.metadata["quinta3_variant"] == "beige"
    assert blue.metadata["quinta3_parameters"]["theme"] == "blue"
    assert beige.metadata["quinta3_parameters"]["theme"] == "beige"

    blue_image = blue_snapshot["internal_roles"]["image"]["relative"]
    beige_image = beige_snapshot["internal_roles"]["image"]["relative"]
    assert blue_image == pytest.approx([0.0, 0.0, 0.9438, 0.8673], abs=1e-4)
    assert beige_image == pytest.approx([0.0, 0.0, 1.0, 1.0], abs=1e-4)


def test_plain_wood_plaque_does_not_create_promotion_or_club_nodes() -> None:
    session = GraphicsSession(GraphicsDocument(name="Wood plaque"))
    slot = create_quinta3_item_slot(session, "quinta3-wood-plaque", variant="plain")

    extras = dict(slot.metadata.get("extra_bindings") or {})
    assert "promotion" not in extras
    assert "club_label" not in extras
    assert not any(key.startswith("app_price_") for key in extras)
    assert slot.metadata["promotion_visible"] is False
    assert slot.metadata["club_visible"] is False
    assert slot.metadata["secondary_price_visible"] is False


def test_variant_geometry_and_semantics_survive_document_roundtrip() -> None:
    session = GraphicsSession(GraphicsDocument(name="Roundtrip"))
    slot = create_quinta3_item_slot(
        session,
        "quinta3-wood-plaque",
        variant="club-promo",
        parameters={"unit": "CADA", "imageCopies": 2},
        x=75,
        y=90,
    )
    serialized = session.document.to_dict()
    reopened = GraphicsDocument.from_dict(serialized)
    reopened_slot = reopened.active_page.slots[slot.id]

    assert reopened_slot.metadata["quinta3_family"] == "quinta3-wood-plaque"
    assert reopened_slot.metadata["quinta3_variant"] == "club-promo"
    assert reopened_slot.metadata["quinta3_parameters"]["unit"] == "CADA"
    assert reopened_slot.metadata["image_copies"] == 2
    extras = reopened_slot.metadata["extra_bindings"]
    assert reopened.active_page.node(extras["promotion"][0]).text == "PROMOÇÃO"
    assert reopened.active_page.node(extras["club_label"][0]).text == "NO SR CLUBE SMART"
    assert all(reopened.active_page.node(node_id) is not None for key, ids in extras.items() for node_id in ids if key.startswith("app_price_"))
