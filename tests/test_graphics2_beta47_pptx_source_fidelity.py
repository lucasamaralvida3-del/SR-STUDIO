"""Measured regression contracts from user-supplied PPTX references.

The Individual has two overlapping cutouts of the *same* product. The Multi
family has a continuous blue strip and source-size typographic proportions.
"""
from __future__ import annotations

import pytest

from srstudio.graphics2.item_slots import (
    bind_product_to_item_slot, create_item_slot, duplicate_item_slot,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession


def session():
    doc = GraphicsDocument(name="PPTX source fidelity")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


def test_individual_source_geometry_has_two_linked_product_cutouts(tmp_path):
    s = session()
    slot = create_item_slot(s, "individual-beta44", x=100, y=200)
    page = s.page
    root = page.node(slot.metadata["root_node_id"])
    assert root.rect.width / root.rect.height == pytest.approx(.94, abs=.015)
    original = page.node(slot.node_by_role[BindingRole.IMAGE.value])
    repeated = page.node(slot.metadata["image_repeat_node_id"])
    assert original.id != repeated.id
    assert repeated.parent_id == root.id
    assert repeated.rect.x > original.rect.x
    assert repeated.rect.x < original.rect.right
    assert repeated.z_index < original.z_index

    # Small real PNG: ID/image propagation must be identical for both cutouts.
    png = tmp_path / "produto.png"
    png.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    ))
    assert bind_product_to_item_slot(s, slot.id, {
        "id": "OLEO-ABC", "name": "OLEO ABC PET 900ML SOJA",
        "price": "7,21", "image_path": str(png),
    })
    assert slot.product_id == "OLEO-ABC"
    assert original.asset_id == repeated.asset_id
    assert original.metadata.get("bound_image_source") == repeated.metadata.get("bound_image_source")
    # Beta64 retains the editable secondary cutout, but hides it by default.
    assert original.visible and not repeated.visible

    # A price-only edit keeps both pictures; a different empty-SKU clears both.
    assert bind_product_to_item_slot(s, slot.id, {"id": "OLEO-ABC", "name": "OLEO ABC", "price": "7,99"})
    assert original.asset_id == repeated.asset_id
    assert bind_product_to_item_slot(s, slot.id, {"id": "NOVO-SKU", "name": "Outro produto", "price": "3,49"})
    assert not original.asset_id and not repeated.asset_id
    assert not original.visible and not repeated.visible


def test_duplicated_individual_never_reuses_other_slots_repeat_image():
    s = session()
    slot = create_item_slot(s, "individual-beta44")
    repeated = slot.metadata["image_repeat_node_id"]
    clone = duplicate_item_slot(s, slot.id)
    cloned_repeated = clone.metadata["image_repeat_node_id"]
    assert cloned_repeated and cloned_repeated != repeated
    assert s.page.node(cloned_repeated).parent_id == clone.metadata["root_node_id"]
    assert not s.page.node(cloned_repeated).visible


@pytest.mark.parametrize("count", [5, 6])
def test_multi_pptx_uses_source_band_and_readable_separate_role_boxes(count):
    s = session()
    info = create_multi_item_strip(s, count=count)
    root = s.page.node(info["root_node_id"]).rect
    footer = next(
        s.page.node(nid) for nid in s.page.node(info["root_node_id"]).children
        if s.page.node(nid).name == "Faixa azul contínua"
    )
    assert footer.rect.y == pytest.approx(root.y + root.height * .70, abs=.01)
    assert footer.rect.height == pytest.approx(root.height * .30, abs=.01)
    assert len(info["slot_ids"]) == count
    for sid in info["slot_ids"]:
        slot = s.page.slots[sid]
        name = s.page.node(slot.node_by_role[BindingRole.NAME.value])
        photo = s.page.node(slot.node_by_role[BindingRole.IMAGE.value])
        integer = s.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value])
        assert name.rect.bottom < photo.rect.y
        assert integer.rect.y >= footer.rect.y
        assert integer.style["font_size"] == pytest.approx(35.6)
        assert slot.metadata["reference_fidelity_revision"] == 47


@pytest.mark.parametrize("mode", ["individual", "six", "seven", "eleven"])
def test_layout_places_original_components_without_stretching(mode):
    from srstudio.graphics2.promotion_layouts import plan_promotion
    from srstudio.graphics2.promotion_composition import apply_slot_composition

    s = session()
    result = apply_slot_composition(s, plan_promotion(mode), reuse_existing=False)
    for root_id in result.root_node_ids:
        node = s.page.node(root_id)
        assert node is not None
        aspect = node.rect.width / node.rect.height
        if node.metadata.get("multi_slot_beta44"):
            assert aspect == pytest.approx(4.75, abs=.015)
        elif node.metadata.get("preset_id") == "individual-beta44":
            assert aspect == pytest.approx(460 / 490, abs=.015)
