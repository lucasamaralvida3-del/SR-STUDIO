from __future__ import annotations

import pytest

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks, is_official_unit_text, semantic_block
from srstudio.graphics2.semantic_placeholders import _is_name_text
from srstudio.graphics2.semantic_vocabulary import semantic_label_role
from srstudio.graphics2.slot_corpus_bindings import bind_product_to_quinta3_slot
from srstudio.graphics2.slot_corpus_calibration import QUINTA3_SUPERVISED_PROFILES
from srstudio.graphics2.slot_corpus_variant_runtime import create_quinta3_item_slot


def _plain_text(text: str, x: float, y: float, w: float, h: float, *, size: float = 24) -> GraphicsNode:
    return GraphicsNode(kind=NodeKind.TEXT, text=text, transform=Transform(x=x, y=y, width=w, height=h), style={"font_size": size})


def _relative(node, root):
    nr = node.rect.normalized()
    rr = root.rect.normalized()
    return [
        (nr.x - rr.x) / rr.width,
        (nr.y - rr.y) / rr.height,
        nr.width / rr.width,
        nr.height / rr.height,
    ]


def test_cada_and_quilo_are_official_structural_units() -> None:
    assert is_official_unit_text("CADA")
    assert is_official_unit_text("QUILO")
    assert is_official_unit_text("/KG")


def test_promotion_and_club_labels_are_never_product_names() -> None:
    forbidden = ["PROMOÇÃO", "NA PROMOÇÃO", "NO SR CLUBE SMART", "NO SRCLUBE", "NO CLUBE SR"]
    for value in forbidden:
        assert semantic_label_role(value) in {"promotion", "club_label"}
        assert _is_name_text(value) is False


def test_card_image_first_recovers_name_before_legacy_price_fallback() -> None:
    document = GraphicsDocument(name="image first")
    page = document.active_page
    image = GraphicsNode(kind=NodeKind.IMAGE, name="produto", asset_id="asset-produto", transform=Transform(x=100, y=100, width=260, height=220))
    name = _plain_text("AMACIANTE VIDA MACIA 1L", 105, 330, 250, 40, size=30)
    promotion = _plain_text("PROMOÇÃO", 360, 260, 100, 25, size=12)
    club = _plain_text("NO SR CLUBE SMART", 360, 290, 150, 25, size=12)
    currency = _plain_text("R$", 350, 350, 35, 40)
    integer = _plain_text("11", 390, 325, 90, 85, size=64)
    decimal = _plain_text(",89", 475, 330, 45, 35)
    unit = _plain_text("CADA", 475, 375, 55, 30)
    for node in (image, name, promotion, club, currency, integer, decimal, unit):
        page.add_node(node)

    build_semantic_blocks(document)

    recovered = [slot for slot in page.slots.values() if slot.metadata.get("semantic_image_first")]
    assert recovered
    slot = recovered[0]
    assert slot.node_by_role[BindingRole.NAME.value] == name.id
    assert slot.node_by_role[BindingRole.UNIT.value] == unit.id
    assert slot.metadata["extra_bindings"]["promotion"] == [promotion.id]
    assert slot.metadata["extra_bindings"]["club_label"] == [club.id]
    assert document.metadata["semantic_recovery_order"] == ["card-image-first", "price-first-fallback"]


def test_secondary_priceblock_is_real_multi_node_semantic_block() -> None:
    session = GraphicsSession(GraphicsDocument(name="secondary block"))
    slot = create_quinta3_item_slot(session, "quinta3-club-side", variant="club-promo")
    build_semantic_blocks(session.document)
    app = semantic_block(session.page, f"priceblock:{slot.id}:app-price")
    assert app is not None
    assert app["metadata"]["split_complete"] is True
    assert set(app["roles"]) == {"currency", "reais", "cents", "unit"}
    assert len(app["members"]) == 4


def test_unit_and_club_visibility_do_not_change_family_preset_id() -> None:
    session = GraphicsSession(GraphicsDocument(name="same family"))
    plain = create_quinta3_item_slot(session, "quinta3-wood-plaque", variant="plain", parameters={"unit": "KG"}, x=10, y=10)
    club = create_quinta3_item_slot(session, "quinta3-wood-plaque", variant="club-promo", parameters={"unit": "CADA"}, x=500, y=10)
    assert plain.metadata["preset_id"] == club.metadata["preset_id"] == "quinta3-wood-plaque"
    assert plain.metadata["club_visible"] is False
    assert club.metadata["club_visible"] is True


def test_blue_and_beige_theme_keep_same_base_family() -> None:
    session = GraphicsSession(GraphicsDocument(name="theme family"))
    blue = create_quinta3_item_slot(session, "quinta3-compact-promo", variant="blue", x=10, y=10)
    beige = create_quinta3_item_slot(session, "quinta3-compact-promo", variant="beige", x=500, y=10)
    assert blue.metadata["preset_id"] == beige.metadata["preset_id"] == "quinta3-compact-promo"
    assert blue.metadata["quinta3_variant"] == "blue"
    assert beige.metadata["quinta3_variant"] == "beige"


def test_image_copies_are_real_nodes_without_creating_family() -> None:
    session = GraphicsSession(GraphicsDocument(name="image copies"))
    slot = create_quinta3_item_slot(
        session,
        "quinta3-compact-promo",
        variant="blue",
        parameters={"supervisedProfile": "odor-boom"},
    )
    extras = slot.metadata["extra_bindings"]
    assert slot.metadata["preset_id"] == "quinta3-compact-promo"
    assert slot.metadata["image_copies"] == 2
    assert len(extras[BindingRole.IMAGE.value]) == 1
    extra_image = session.page.node(extras[BindingRole.IMAGE.value][0])
    assert extra_image is not None and extra_image.kind is NodeKind.IMAGE

    bind_product_to_quinta3_slot(session, slot.id, {"id": "odor", "name": "ODOR BOOM", "price": "19,43", "unit": "UN", "image_asset_id": "asset-odor"})
    primary = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    extra_image = session.page.node(extras[BindingRole.IMAGE.value][0])
    assert extra_image.asset_id == primary.asset_id


def test_supervised_profiles_materialize_exact_role_geometry() -> None:
    # Exact per-example calibration is the reconstruction loop output.  The
    # runtime must reproduce the frozen relative geometry without threshold
    # relaxation or family proliferation.
    for profile_id, profile in QUINTA3_SUPERVISED_PROFILES.items():
        session = GraphicsSession(GraphicsDocument(name=profile_id))
        slot = create_quinta3_item_slot(
            session,
            profile["family_id"],
            variant=profile["variant"],
            parameters={"supervisedProfile": profile_id},
            x=50,
            y=60,
        )
        root = session.page.node(slot.metadata["root_node_id"])
        areas = slot.metadata["role_area_nodes"]
        for role in ("image", "name", "price", "unit"):
            node = session.page.node(areas[role])
            assert _relative(node, root) == pytest.approx(profile["roleBounds"][role], abs=1e-6)
        extras = slot.metadata.get("extra_bindings") or {}
        if "secondaryPrice" in profile["roleBounds"]:
            group_id = next(node_id for node_id in slot.metadata["quinta3_variant_nodes"] if session.page.node(node_id).name == "SECONDARY PRICE AREA")
            assert _relative(session.page.node(group_id), root) == pytest.approx(profile["roleBounds"]["secondaryPrice"], abs=1e-6)
            for key in ("app_price_currency", "app_price_integer", "app_price_cents", "app_unit"):
                assert len(extras[key]) == 1
        if "promotion" in profile["roleBounds"]:
            assert _relative(session.page.node(extras["promotion"][0]), root) == pytest.approx(profile["roleBounds"]["promotion"], abs=1e-6)
        if "club" in profile["roleBounds"]:
            assert _relative(session.page.node(extras["club_label"][0]), root) == pytest.approx(profile["roleBounds"]["club"], abs=1e-6)
        assert slot.metadata["preset_id"] == profile["family_id"]


def test_literal_unit_secondary_nodes_and_variant_parameters_survive_roundtrip() -> None:
    session = GraphicsSession(GraphicsDocument(name="roundtrip fidelity"))
    slot = create_quinta3_item_slot(session, "quinta3-club-side", variant="club-promo", parameters={"supervisedProfile": "amaciante"})
    assert bind_product_to_quinta3_slot(session, slot.id, {"id": "amaciante", "name": "AMACIANTE VIDA MACIA 1L", "price": "11,89", "secondary_price": "12,66", "unit": "CADA", "secondary_unit": "UN"})
    assert session.page.node(slot.node_by_role[BindingRole.UNIT.value]).text == "CADA"
    extras = slot.metadata["extra_bindings"]
    assert session.page.node(extras["app_unit"][0]).text == "UN"

    reopened = GraphicsDocument.from_dict(session.document.to_dict())
    reopened_slot = reopened.active_page.slots[slot.id]
    assert reopened_slot.metadata["preset_id"] == "quinta3-club-side"
    assert reopened_slot.metadata["quinta3_variant"] == "club-promo"
    assert reopened_slot.metadata["supervised_profile"] == "amaciante"
    assert reopened_slot.metadata["quinta3_parameters"]["supervisedProfile"] == "amaciante"
    assert reopened_slot.metadata["quinta3_parameters"]["roleBounds"] == QUINTA3_SUPERVISED_PROFILES["amaciante"]["roleBounds"]
