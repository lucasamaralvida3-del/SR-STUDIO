from __future__ import annotations

import json
import math
import zipfile

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter, _bridge_save_wrapper
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage, Rect
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID, MEAT_STRIP_FULL_CARD_PROFILES
from srstudio.graphics2.slot_corpus_meat_strip_ownership import (
    PROFILE_ORDER,
    ownership_snapshot,
    strip_ownership_snapshot,
)


PRODUCTS = {
    "costela": {"id": "prod-costela", "name": "COSTELA GAÚCHA", "price": "24.79", "unit": "KG"},
    "pernil": {"id": "prod-pernil", "name": "PERNIL SUÍNO S/ OSSO", "price": "19.99", "unit": "KG"},
    "musculo": {"id": "prod-musculo", "name": "MÚSCULO BOVINO", "price": "26.90", "unit": "KG"},
    "moela": {"id": "prod-moela", "name": "MOELA DE FRANGO", "price": "12.49", "unit": "KG"},
}


def _session() -> GraphicsSession:
    document = GraphicsDocument(name="Quinta3 Meat ownership")
    document.pages = [GraphicsPage(name="Página 1", width=1080, height=1350, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    return GraphicsSession(document)


def _four_bound_cells() -> tuple[GraphicsSession, list]:
    session = _session()
    router = ItemSlotCommandRouter(session)
    slots = []
    for expected_profile in PROFILE_ORDER:
        result = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        assert result.ok and result.changed, result.to_dict()
        slot = session.page.slots[result.payload["slot_id"]]
        assert slot.metadata["full_card_profile"] == expected_profile
        product = dict(PRODUCTS[expected_profile])
        product["quinta3_supervised_profile"] = expected_profile
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        assert bound.ok and bound.changed, bound.to_dict()
        slots.append(slot)
    return session, slots


def _tree_rects(page, root_id: str) -> dict[str, tuple[float, float, float, float]]:
    return {
        node_id: (
            page.nodes[node_id].transform.x,
            page.nodes[node_id].transform.y,
            page.nodes[node_id].transform.width,
            page.nodes[node_id].transform.height,
        )
        for node_id in [root_id, *page.descendants(root_id)]
    }


def _assert_rect_equal(actual, expected) -> None:
    assert actual[0] == pytest.approx(expected[0])
    assert actual[1] == pytest.approx(expected[1])
    assert actual[2] == pytest.approx(expected[2])
    assert actual[3] == pytest.approx(expected[3])


def test_meat_strip_is_one_container_with_four_unique_product_cells() -> None:
    session, slots = _four_bound_cells()
    page = session.page

    strip_ids = {str(slot.metadata.get("meat_strip_root_id") or "") for slot in slots}
    assert len(strip_ids) == 1
    strip_id = next(iter(strip_ids))
    strip = page.node(strip_id)
    assert strip is not None
    assert strip.metadata["ownership_model"] == "single-strip-container-with-product-cells"
    assert strip.metadata["cell_count"] == 4
    assert strip.metadata["ownership_complete"] is True

    runtime_sets: list[set[str]] = []
    role_sets: list[set[str]] = []
    for expected_profile, slot in zip(PROFILE_ORDER, slots):
        snapshot = ownership_snapshot(page, slot)
        root_id = snapshot["slot_root_id"]
        assert snapshot["parent_id"] == strip_id
        assert snapshot["role"] == "product_cell"
        assert snapshot["owner_slot_cell"] == slot.id
        assert slot.product_id == PRODUCTS[expected_profile]["id"]
        assert slot.metadata["runtime_node_ids_unique"] is True
        assert slot.metadata["source_node_ids_shared_by_provenance_only"] is True
        runtime_sets.append(set(snapshot["runtime_node_ids"]))
        role_sets.append(set(slot.node_by_role.values()))

        root = page.node(root_id)
        assert root is not None and root.metadata["product_cell_root"] is True
        assert root.parent_id == strip_id
        assert set(slot.node_by_role.values()) <= set(page.descendants(root_id))
        # Shared PPTX row nodes are dependencies of the strip root, never owned
        # by a mutable ProductCell subtree.
        shared_source_ids = {"2", "3", "4", "5", "6", "7"}
        owned_source_ids = {
            str(page.nodes[node_id].metadata.get("source_shape_id") or "")
            for node_id in snapshot["runtime_node_ids"]
        }
        assert not (shared_source_ids & owned_source_ids)

    for index, owned in enumerate(runtime_sets):
        for other in runtime_sets[index + 1 :]:
            assert owned.isdisjoint(other)
    for index, roles in enumerate(role_sets):
        for other in role_sets[index + 1 :]:
            assert roles.isdisjoint(other)

    strip_snapshot = strip_ownership_snapshot(page, strip_id)
    assert strip_snapshot["cell_slot_ids"] == [slot.id for slot in slots]
    assert len(set(strip_snapshot["cell_root_ids"])) == 4
    assert len(set(strip_snapshot["shared_visual_nodes"])) == 7
    shared_nodes = set(strip_snapshot["shared_visual_nodes"])
    assert all(shared_nodes.isdisjoint(owned) for owned in runtime_sets)

    source_ids = {
        str(page.nodes[node_id].metadata.get("source_shape_id") or "")
        for node_id in shared_nodes
    }
    assert {"2", "3", "4", "5", "6", "7"} <= source_ids
    assert any(page.nodes[node_id].metadata.get("source_kind") == "inherited-slide-background" for node_id in shared_nodes)


def test_product_cell_transforms_match_source_positions_inside_shared_strip() -> None:
    session, slots = _four_bound_cells()
    page = session.page
    strip = page.node(slots[0].metadata["meat_strip_root_id"])
    assert strip is not None
    strip_rect = strip.rect.normalized()

    source_roots = [MEAT_STRIP_FULL_CARD_PROFILES[profile]["root_emu"] for profile in PROFILE_ORDER]
    left = min(float(root[0]) for root in source_roots)
    top = min(float(root[1]) for root in source_roots)
    right = max(float(root[0]) + float(root[2]) for root in source_roots)
    bottom = max(float(root[1]) + float(root[3]) for root in source_roots)
    source_strip = Rect(left, top, right - left, bottom - top)

    for profile_id, slot in zip(PROFILE_ORDER, slots):
        source = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]["root_emu"]
        root = page.node(slot.metadata["root_node_id"])
        assert root is not None
        actual = root.rect.normalized()
        expected = Rect(
            strip_rect.x + ((float(source[0]) - source_strip.x) / source_strip.width) * strip_rect.width,
            strip_rect.y + ((float(source[1]) - source_strip.y) / source_strip.height) * strip_rect.height,
            (float(source[2]) / source_strip.width) * strip_rect.width,
            (float(source[3]) / source_strip.height) * strip_rect.height,
        )
        _assert_rect_equal(
            (actual.x, actual.y, actual.width, actual.height),
            (expected.x, expected.y, expected.width, expected.height),
        )
        relative = slot.metadata["cell_relative_transform"]
        assert relative["x"] == pytest.approx((actual.x - strip_rect.x) / strip_rect.width)
        assert relative["y"] == pytest.approx((actual.y - strip_rect.y) / strip_rect.height)
        assert relative["width"] == pytest.approx(actual.width / strip_rect.width)
        assert relative["height"] == pytest.approx(actual.height / strip_rect.height)


def test_move_one_product_cell_moves_only_its_owned_subtree() -> None:
    session, slots = _four_bound_cells()
    page = session.page
    target = slots[0]  # COSTELA
    target_root = str(target.metadata["root_node_id"])
    strip_id = str(target.metadata["meat_strip_root_id"])

    before_cells = {slot.id: _tree_rects(page, str(slot.metadata["root_node_id"])) for slot in slots}
    before_shared = _tree_rects(page, strip_id)
    # Compare only shared/root nodes outside all ProductCell subtrees.
    cell_nodes = set().union(*(set(rects) for rects in before_cells.values()))
    before_shared_only = {node_id: rect for node_id, rect in before_shared.items() if node_id not in cell_nodes}

    session.selection = {target_root}
    session.anchor_id = target_root
    session.move_selected(37.0, 19.0)

    after_target = _tree_rects(page, target_root)
    for node_id, before in before_cells[target.id].items():
        actual = after_target[node_id]
        assert actual[0] == pytest.approx(before[0] + 37.0)
        assert actual[1] == pytest.approx(before[1] + 19.0)
        assert actual[2] == pytest.approx(before[2])
        assert actual[3] == pytest.approx(before[3])

    for slot in slots[1:]:
        assert _tree_rects(page, str(slot.metadata["root_node_id"])) == before_cells[slot.id]

    after_shared = _tree_rects(page, strip_id)
    for node_id, before in before_shared_only.items():
        _assert_rect_equal(after_shared[node_id], before)


def test_resize_musculo_scales_only_its_owned_subtree() -> None:
    session, slots = _four_bound_cells()
    page = session.page
    target = slots[2]  # MUSCULO
    target_root_id = str(target.metadata["root_node_id"])
    target_root = page.node(target_root_id)
    assert target_root is not None
    old = target_root.rect.normalized()

    before_cells = {slot.id: _tree_rects(page, str(slot.metadata["root_node_id"])) for slot in slots}
    strip_id = str(target.metadata["meat_strip_root_id"])
    before_strip = _tree_rects(page, strip_id)
    cell_nodes = set().union(*(set(rects) for rects in before_cells.values()))
    before_shared_only = {node_id: rect for node_id, rect in before_strip.items() if node_id not in cell_nodes}

    new = Rect(old.x, old.y, old.width * 1.25, old.height * 0.85)
    session.resize_node(target_root_id, x=new.x, y=new.y, width=new.width, height=new.height)

    after = _tree_rects(page, target_root_id)
    for node_id, before in before_cells[target.id].items():
        rel_x = (before[0] - old.x) / old.width
        rel_y = (before[1] - old.y) / old.height
        rel_w = before[2] / old.width
        rel_h = before[3] / old.height
        expected = (
            new.x + rel_x * new.width,
            new.y + rel_y * new.height,
            rel_w * new.width,
            rel_h * new.height,
        )
        _assert_rect_equal(after[node_id], expected)

    for slot in (slots[0], slots[1], slots[3]):
        assert _tree_rects(page, str(slot.metadata["root_node_id"])) == before_cells[slot.id]

    after_strip = _tree_rects(page, strip_id)
    for node_id, before in before_shared_only.items():
        _assert_rect_equal(after_strip[node_id], before)


def test_save_package_serializes_four_cells_and_reopens_four_with_content(tmp_path) -> None:
    session, slots = _four_bound_cells()
    page = session.page
    before_slot_ids = [slot.id for slot in slots]
    before_product_ids = [slot.product_id for slot in slots]
    before_roots = {slot.id: _tree_rects(page, str(slot.metadata["root_node_id"])) for slot in slots}
    before_images = {
        slot.id: {
            "source_shape_id": page.nodes[slot.node_by_role[BindingRole.IMAGE.value]].metadata.get("source_shape_id"),
            "image_sha256": page.nodes[slot.node_by_role[BindingRole.IMAGE.value]].metadata.get("image_sha256"),
            "pptx_internal_media": page.nodes[slot.node_by_role[BindingRole.IMAGE.value]].metadata.get("pptx_internal_media"),
        }
        for slot in slots
    }

    output = tmp_path / "quinta3-meat-strip.srscene"
    save_package(session.document, output, embed_local_assets=False)

    with zipfile.ZipFile(output, "r") as archive:
        scene = json.loads(archive.read("scene.json").decode("utf-8"))
    serialized_slots = scene["pages"][0]["slots"]
    assert len(serialized_slots) == 4
    assert set(serialized_slots) == set(before_slot_ids)

    reopened = load_package(output)
    reopened_page = reopened.active_page
    assert len(reopened_page.slots) == 4
    assert list(reopened_page.slots) == before_slot_ids
    assert [reopened_page.slots[slot_id].product_id for slot_id in before_slot_ids] == before_product_ids

    strip_ids = {str(reopened_page.slots[slot_id].metadata.get("meat_strip_root_id") or "") for slot_id in before_slot_ids}
    assert len(strip_ids) == 1
    strip = reopened_page.node(next(iter(strip_ids)))
    assert strip is not None and strip.metadata["ownership_complete"] is True

    for slot_id in before_slot_ids:
        restored = reopened_page.slots[slot_id]
        assert restored.metadata["preset_id"] == MEAT_FAMILY_ID
        assert restored.metadata["owner_kind"] == "product_cell"
        assert _tree_rects(reopened_page, str(restored.metadata["root_node_id"])) == before_roots[slot_id]
        image = reopened_page.node(restored.node_by_role[BindingRole.IMAGE.value])
        name = reopened_page.node(restored.node_by_role[BindingRole.NAME.value])
        currency = reopened_page.node(restored.node_by_role[BindingRole.CURRENCY.value])
        integer = reopened_page.node(restored.node_by_role[BindingRole.PRICE_REAIS.value])
        decimal = reopened_page.node(restored.node_by_role[BindingRole.PRICE_CENTS.value])
        unit = reopened_page.node(restored.node_by_role[BindingRole.UNIT.value])
        assert all(node is not None for node in (image, name, currency, integer, decimal, unit))
        assert {
            "source_shape_id": image.metadata.get("source_shape_id"),
            "image_sha256": image.metadata.get("image_sha256"),
            "pptx_internal_media": image.metadata.get("pptx_internal_media"),
        } == before_images[slot_id]
        assert name.text
        assert currency.text == "R$"
        assert integer.text
        assert decimal.text
        assert unit.text == "KG"


def test_full_studio_bridge_save_mirrors_selected_copy_into_canonical_session(tmp_path) -> None:
    session, _ = _four_bound_cells()
    canonical = tmp_path / "graphics2-bridge" / "project.srscene"
    selected_copy = tmp_path / "manual-copy.srscene"

    mirrored = _bridge_save_wrapper(save_package, canonical)
    written = mirrored(session.document, selected_copy, embed_local_assets=False)

    assert written == selected_copy
    assert selected_copy.is_file()
    assert canonical.is_file()
    selected = load_package(selected_copy)
    reopened_from_full_studio = load_package(canonical)
    assert len(selected.active_page.slots) == 4
    assert len(reopened_from_full_studio.active_page.slots) == 4
    assert selected.to_dict() == reopened_from_full_studio.to_dict()
