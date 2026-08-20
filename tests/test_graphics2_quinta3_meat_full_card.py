from __future__ import annotations

import math

import pytest

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage, NodeKind
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.slot_corpus_full_card import (
    MEAT_FAMILY_ID,
    MEAT_STRIP_FULL_CARD_PROFILES,
    MEAT_STRIP_SOURCE_CLUSTER_NODE_COUNT,
    MEAT_STRIP_SOURCE_PAGE_BACKGROUND,
    MEAT_STRIP_SOURCE_STRIP_FILL,
    SOURCE_SHA256,
)
from srstudio.graphics2.slot_corpus_full_card_gate import evaluate_meat_full_card
from srstudio.graphics2.slot_corpus_variant_runtime import create_quinta3_item_slot


EXPECTED_POSITIONS = {
    "costela": "first",
    "pernil": "middle",
    "musculo": "middle",
    "moela": "last",
}


def _session() -> GraphicsSession:
    document = GraphicsDocument(name="Quinta3 Meat Full Card")
    document.pages = [GraphicsPage(name="Página 1", width=1080, height=1350, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    return GraphicsSession(document)


def _slot(profile_id: str):
    session = _session()
    slot = create_quinta3_item_slot(
        session,
        MEAT_FAMILY_ID,
        variant="default",
        parameters={"supervisedProfile": profile_id},
        x=80,
        y=120,
    )
    return session, slot


def test_source_contract_records_the_real_shared_meat_cluster_not_role_union_only() -> None:
    assert MEAT_STRIP_SOURCE_CLUSTER_NODE_COUNT == 30
    assert set(MEAT_STRIP_FULL_CARD_PROFILES) == {"costela", "pernil", "musculo", "moela"}
    assert SOURCE_SHA256 == "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"


@pytest.mark.parametrize("profile_id", ["costela", "pernil", "musculo", "moela"])
def test_full_card_gate_passes_for_all_four_real_meat_examples(profile_id: str) -> None:
    session, slot = _slot(profile_id)
    report = evaluate_meat_full_card(session.page, slot, profile_id=profile_id)

    assert report.ok, report.to_dict()
    assert slot.metadata["full_card_visual"] is True
    assert slot.metadata["full_card_source_cluster_node_count"] == 30
    assert slot.metadata["full_card_source_sha256"] == SOURCE_SHA256
    assert slot.metadata["full_card_strip_position"] == EXPECTED_POSITIONS[profile_id]
    assert report.reconstructed_subtree_node_count == report.expected_reconstructed_subtree_node_count
    assert report.visual_decorative_node_count == report.expected_visual_decorative_node_count


@pytest.mark.parametrize("profile_id", ["costela", "pernil", "musculo", "moela"])
def test_meat_full_card_has_source_visual_nodes_and_no_synthetic_role_backplates(profile_id: str) -> None:
    session, slot = _slot(profile_id)
    root = session.page.node(slot.metadata["root_node_id"])
    assert root is not None
    subtree = [session.page.node(node_id) for node_id in [root.id, *session.page.descendants(root.id)]]
    subtree = [node for node in subtree if node is not None]

    assert not any(node.metadata.get("item_slot_image_backplate") for node in subtree)
    assert not any(node.metadata.get("item_slot_price_background") for node in subtree)

    visuals = [session.page.node(node_id) for node_id in slot.metadata["full_card_visual_nodes"]]
    visuals = [node for node in visuals if node is not None]
    background = next(node for node in visuals if node.metadata.get("source_kind") == "inherited-slide-background")
    strip = next(node for node in visuals if str(node.metadata.get("source_shape_id") or "") == "3")
    source_group = next(node for node in visuals if str(node.metadata.get("source_shape_id") or "") == "2")
    source_overlay = next(node for node in visuals if str(node.metadata.get("source_shape_id") or "") == "4")

    assert background.kind is NodeKind.RECT
    assert background.style["fill"] == MEAT_STRIP_SOURCE_PAGE_BACKGROUND
    assert strip.kind is NodeKind.PATH
    assert strip.style["fill"] == MEAT_STRIP_SOURCE_STRIP_FILL
    assert strip.metadata["source_geometry"] == "custGeom"
    assert strip.metadata["custom_path"]["paths"][0]["commands"]
    assert source_group.kind is NodeKind.GROUP
    assert source_overlay.kind is NodeKind.RECT
    assert source_overlay.style["fill"] == "transparent"


@pytest.mark.parametrize("profile_id", ["costela", "pernil", "musculo", "moela"])
def test_exact_source_semantic_styles_and_z_order_are_materialized(profile_id: str) -> None:
    session, slot = _slot(profile_id)
    profile = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
    mapping = {
        "image": BindingRole.IMAGE,
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }
    for key, binding in mapping.items():
        node = session.page.node(slot.node_by_role[binding.value])
        spec = profile["roles"][key]
        assert node is not None
        assert node.metadata["source_shape_id"] == str(spec["source_id"])
        assert node.z_index == spec["z"]
        assert node.opacity == pytest.approx(1.0)
        assert node.transform.rotation == pytest.approx(0.0)
        if key != "image":
            expected_style = spec["style"]
            assert node.style["font_family"] == "Anton"
            assert node.style["font_size"] == pytest.approx(expected_style["font_size"])
            assert node.style["font_weight"] == 400
            assert node.style["color"] == "#FFFFFF"
            assert node.style["v_align"] == "top"
            assert node.style["fit_inside_box"] is False
            assert node.style["letter_spacing_pt"] == pytest.approx(expected_style["letter_spacing_pt"])


def test_musculo_preserves_nonzero_drawingml_fillrect_and_axis_aligned_custgeom_contract() -> None:
    session, slot = _slot("musculo")
    image = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    assert image is not None
    assert image.kind is NodeKind.IMAGE
    assert image.style["fit"] == "fill"
    assert image.style["fill_rect"] == {"l": 0.0, "t": -0.10057, "r": 0.0, "b": -0.40571}
    assert image.metadata["source_geometry"] == "custGeom-axis-aligned-rect"
    assert image.metadata.get("clip_path") in (None, {})
    assert image.metadata["pptx_fill_rect"]["has_outset"] is True


def test_source_assets_are_frozen_with_identity_and_provenance() -> None:
    expected = {
        "costela": ("/ppt/media/image3.png", "9458fe6054535e4411834407c9af9af24f35d2946f8f027f26f416023a441e3d"),
        "pernil": ("/ppt/media/image5.png", "2dbde9ce6a7cae99bee9d25647af23b3134b1ad680fdbd558946cb05edfcae0e"),
        "musculo": ("/ppt/media/image4.png", "3a747c31bfe3aa8ae2326ec91f523f59c400aab069f3d3e94512c500b3a1fad3"),
        "moela": ("/ppt/media/image6.png", "b2b40eb4f871b131d4c21d7ae40d7a9d0c4232c740ef8fa396b01f1948c35524"),
    }
    for profile_id, (media, digest) in expected.items():
        asset = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]["image_asset"]
        assert asset["internal_media"] == media
        assert asset["sha256"] == digest


def test_full_card_subtree_survives_save_reopen_without_losing_source_contract() -> None:
    session, slot = _slot("costela")
    before = evaluate_meat_full_card(session.page, slot, profile_id="costela")
    assert before.ok, before.to_dict()

    reopened = GraphicsDocument.from_dict(session.document.to_dict())
    restored = reopened.active_page.slots[slot.id]
    after = evaluate_meat_full_card(reopened.active_page, restored, profile_id="costela")

    assert after.ok, after.to_dict()
    assert after.reconstructed_subtree_node_count == before.reconstructed_subtree_node_count
    assert restored.metadata["full_card_source_sha256"] == SOURCE_SHA256


def test_other_four_families_are_not_advanced_to_full_card_in_this_round() -> None:
    session = _session()
    for family_id, profile_id, variant in (
        ("quinta3-wood-plaque", "bolacha", "plain"),
        ("quinta3-compact-promo", "odor-boom", "blue"),
        ("quinta3-club-side", "amaciante", "club-promo"),
        ("quinta3-stationery-round", "cadernos", "default"),
    ):
        slot = create_quinta3_item_slot(
            session,
            family_id,
            variant=variant,
            parameters={"supervisedProfile": profile_id},
            x=40,
            y=50,
        )
        assert slot.metadata.get("full_card_visual") is not True
        assert not slot.metadata.get("full_card_visual_nodes")


def test_meat_root_aspect_ratio_comes_from_full_visual_card_partition_not_old_role_union() -> None:
    session, slot = _slot("costela")
    root = session.page.node(slot.metadata["root_node_id"])
    assert root is not None
    source = MEAT_STRIP_FULL_CARD_PROFILES["costela"]["root_emu"]
    expected_ratio = source[3] / source[2]
    assert math.isclose(root.transform.height / root.transform.width, expected_ratio, rel_tol=1e-9)
