from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import list_item_slot_presets
from srstudio.graphics2.model import BindingRole, GraphicsDocument
from srstudio.graphics2.multi_item_slots import (
    is_multi_item_root,
    product_cells_for_root,
    validate_multi_item_ownership,
)
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity
from srstudio.graphics2.slot_family_inventory import (
    INVENTORY_PATH,
    cached_slot_asset_path,
    load_slot_family_inventory,
    multi_item_family_ids,
    single_item_family_ids,
    slot_family_entries,
    slot_font_family,
)


EXPECTED_MULTI = {
    "quinta3-meat-strip": 4,
    "quinta3-compact-blue-strip": 4,
    "quinta3-compact-beige-strip": 3,
}


def _router() -> ItemSlotCommandRouter:
    return ItemSlotCommandRouter(GraphicsSession(GraphicsDocument(name="All real slot families")))


def _product(index: int, *, image: str = "wide.png", name: str | None = None) -> dict:
    return {
        "id": f"product-{index}",
        "name": name or f"PRODUTO GENÉRICO {index}",
        "price": f"{index + 10}.9{index}",
        "retail_price": f"{index + 11}.8{index}",
        "secondary_price": f"{index + 9}.7{index}",
        "unit": "UN" if index % 2 else "KG",
        "image_path": image,
        "image_asset_id": f"asset-{index}",
        "promotion_label": "PROMOÇÃO",
    }


def _relative_snapshot(page, root_id: str) -> dict[str, tuple[float, float, float, float]]:
    root = page.node(root_id)
    assert root is not None
    bounds = root.rect.normalized()
    result = {}
    for node_id in page.descendants(root_id):
        node = page.node(node_id)
        assert node is not None
        rect = node.rect.normalized()
        result[node_id] = (
            (rect.x - bounds.x) / bounds.width,
            (rect.y - bounds.y) / bounds.height,
            rect.width / bounds.width,
            rect.height / bounds.height,
        )
    return result


def test_inventory_is_complete_neutral_and_schema_valid() -> None:
    inventory = load_slot_family_inventory()
    assert INVENTORY_PATH.name == "slot-family-inventory.json"
    assert inventory["SOURCE_SHA256"] == "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
    assert inventory["FAMILIES_TOTAL"] == 17
    assert inventory["SINGLE_ITEM_FAMILIES"] == 14
    assert inventory["MULTI_ITEM_FAMILIES"] == 3
    assert inventory["PRODUCT_CATEGORY_HARDCODING"] is False
    assert len(slot_family_entries()) == 17
    assert len(single_item_family_ids()) == 14
    assert set(multi_item_family_ids()) == set(EXPECTED_MULTI)

    forbidden = ("if category", "product_name contains", "sku ==", "image looks like")
    text = INVENTORY_PATH.read_text(encoding="utf-8").casefold()
    assert all(token not in text for token in forbidden)
    for family in inventory["FAMILIES"]:
        assert family["FAMILY_ID"].startswith("quinta3-")
        assert family["IMAGE_RULE"]["category_restriction"] is False
        assert family["UNIT_RULE"]["family_discriminator"] is False
        assert family["IMPLEMENTATION_STATUS"] == "IMPLEMENTED"
        assert family["TEST_STATUS"] == "PASS"
        assert family["VISUAL_STATUS"] == "PASS"
        assert family["USABLE_STATUS"] is True


def test_real_studio_catalog_exposes_all_families_with_type_and_cell_count() -> None:
    router = _router()
    payload = router.payload()
    catalog = {
        item["id"]: item
        for item in payload["editor"]["item_slot_presets"]
        if str(item["id"]).startswith("quinta3-")
    }
    assert set(catalog) == {item["FAMILY_ID"] for item in slot_family_entries()}
    for family_id, preset in catalog.items():
        expected = EXPECTED_MULTI.get(family_id, 1)
        assert preset["product_cell_count"] == expected
        assert preset["slot_kind"] == ("multi_item" if family_id in EXPECTED_MULTI else "single_item")
        assert preset["catalog_name"]


@pytest.mark.parametrize("family_id", single_item_family_ids())
def test_every_single_item_family_is_creatable_bindable_and_generic(family_id: str) -> None:
    router = _router()
    created = router.dispatch({"name": "add_item_slot", "preset_id": family_id})
    assert created.ok and created.changed
    slot = router.session.page.slots[created.payload["slot_id"]]
    assert not is_multi_item_root(slot)
    assert set(slot.node_by_role) >= {
        BindingRole.IMAGE.value,
        BindingRole.NAME.value,
        BindingRole.CURRENCY.value,
        BindingRole.PRICE_REAIS.value,
        BindingRole.PRICE_CENTS.value,
        BindingRole.UNIT.value,
    }
    image_node = router.session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    name_node = router.session.page.node(slot.node_by_role[BindingRole.NAME.value])
    assert image_node is not None and name_node is not None
    behavior = deepcopy(image_node.style)
    assert name_node.style.get("fit_inside_box") is True

    first = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": _product(1, image="wide.png", name="CURTO")})
    second = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot.id,
            "product": _product(2, image="tall.png", name="NOME DE PRODUTO TOTALMENTE DIFERENTE E MAIS LONGO PARA TESTAR WRAP"),
        }
    )
    assert first.ok and second.ok
    assert slot.product_id == "product-2"
    assert image_node.metadata["bound_image_source"] == "tall.png"
    assert image_node.style == behavior
    assert name_node.text.startswith("NOME DE PRODUTO TOTALMENTE")
    assert name_node.style.get("fit_inside_box") is True
    assert_document_integrity(router.session.document)


@pytest.mark.parametrize("family_id,expected_cells", EXPECTED_MULTI.items())
def test_multi_item_root_has_shared_visuals_and_independent_product_cells(family_id: str, expected_cells: int) -> None:
    router = _router()
    created = router.dispatch({"name": "add_item_slot", "preset_id": family_id, "x": 40, "y": 60})
    assert created.ok
    root = router.session.page.slots[created.payload["slot_id"]]
    cells = product_cells_for_root(router.session.page, root.id)
    ownership = validate_multi_item_ownership(router.session.page, root)
    assert ownership == {
        "root_count": 1,
        "product_cell_count": expected_cells,
        "shared_visual_owner": root.id,
        "cell_nodes_unique": True,
    }
    assert len(root.metadata["shared_visual_nodes"]) >= expected_cells
    assert all(cell.metadata["multi_item_root_slot_id"] == root.id for cell in cells)

    for index, cell in enumerate(cells):
        before = {other.id: deepcopy(other.metadata["product_snapshot"]) for other in cells if other.id != cell.id}
        result = router.dispatch(
            {
                "name": "bind_product",
                "slot_id": cell.id,
                "product": _product(index, image="wide.png" if index % 2 == 0 else "tall.png"),
            }
        )
        assert result.ok and result.changed
        assert cell.product_id == f"product-{index}"
        assert all(other.metadata["product_snapshot"] == before[other.id] for other in cells if other.id != cell.id)

    assert root.metadata["state"] == "filled"
    changed_cell = cells[1]
    sibling_ids = [cell.product_id for cell in cells]
    replace = router.dispatch({"name": "bind_product", "slot_id": changed_cell.id, "product": _product(99, image="other-category.png")})
    assert replace.ok
    assert [cell.product_id for cell in cells] == [sibling_ids[0], "product-99", *sibling_ids[2:]]
    assert_document_integrity(router.session.document)


@pytest.mark.parametrize("family_id,expected_cells", EXPECTED_MULTI.items())
def test_multi_item_move_resize_save_reopen_and_edit_after_reopen(tmp_path: Path, family_id: str, expected_cells: int) -> None:
    router = _router()
    created = router.dispatch({"name": "add_item_slot", "preset_id": family_id, "x": 35, "y": 45})
    root_slot = router.session.page.slots[created.payload["slot_id"]]
    cells = product_cells_for_root(router.session.page, root_slot.id)
    for index, cell in enumerate(cells):
        assert router.dispatch({"name": "bind_product", "slot_id": cell.id, "product": _product(index)}).ok

    root_id = str(root_slot.metadata["root_node_id"])
    root_node = router.session.page.node(root_id)
    assert root_node is not None
    before_move = _relative_snapshot(router.session.page, root_id)
    router.session.selection = {root_id}
    router.session.anchor_id = root_id
    router.session.move_selected(31, 27)
    after_move = _relative_snapshot(router.session.page, root_id)
    assert set(after_move) == set(before_move)
    for node_id, relative in before_move.items():
        assert after_move[node_id] == pytest.approx(relative, abs=1e-12)

    moved = root_node.rect.normalized()
    router.session.resize_node(root_id, x=moved.x - 8, y=moved.y - 5, width=moved.width * 1.35, height=moved.height * 1.22)
    after_resize = _relative_snapshot(router.session.page, root_id)
    assert set(after_resize) == set(before_move)
    for node_id, relative in before_move.items():
        for actual, expected in zip(after_resize[node_id], relative):
            if expected == 0.0:
                # GraphicsSession keeps every resized axis editable with its
                # existing 0.1 px minimum. A vertical LINE therefore changes
                # only from mathematical zero to a sub-pixel relative width.
                assert actual <= 0.001
            else:
                assert actual == pytest.approx(expected, abs=1e-12)
    validate_multi_item_ownership(router.session.page, root_slot)

    output = tmp_path / f"{family_id}.srscene"
    save_package(router.session.document, output)
    reopened = load_package(output)
    assert_document_integrity(reopened)
    reopened_root = reopened.active_page.slots[root_slot.id]
    reopened_cells = product_cells_for_root(reopened.active_page, reopened_root.id)
    assert len(reopened_cells) == expected_cells
    assert [cell.product_id for cell in reopened_cells] == [f"product-{index}" for index in range(expected_cells)]
    validate_multi_item_ownership(reopened.active_page, reopened_root)

    reopened_router = ItemSlotCommandRouter(GraphicsSession(reopened))
    edit = reopened_router.dispatch({"name": "bind_product", "slot_id": reopened_cells[-1].id, "product": _product(88, image="different-category.png")})
    assert edit.ok
    assert reopened_cells[-1].product_id == "product-88"
    assert [cell.product_id for cell in reopened_cells[:-1]] == [f"product-{index}" for index in range(expected_cells - 1)]


def test_qml_catalog_shows_single_multi_and_cell_counts() -> None:
    qml = Path("src/srstudio/graphics2/qml/ProjectActions.qml").read_text(encoding="utf-8")
    assert "modelData.slot_kind" in qml
    assert "modelData.product_cell_count" in qml
    assert "MULTI" in qml
    assert "CÉLULAS" in qml
    assert "Limpar produto" in qml


def test_multi_item_move_and_resize_use_local_preview_and_one_release_commit() -> None:
    qml = Path("src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    node_drag = qml[qml.index("drag.target: parent") : qml.index("onDoubleClicked:", qml.index("drag.target: parent"))]
    selection_overlay = qml.index("id: selectionOverlay")
    handle_start = qml.index('"dir":"nw"', selection_overlay)
    resize_handles = qml[handle_start : qml.index("WheelHandler", handle_start)]
    assert "onPositionChanged" not in node_drag
    assert node_drag.split("onReleased:", 1)[0].count("sceneBridge") == 1  # selection on press only
    assert node_drag.count("sceneBridge.moveSelectionAtZoom") == 1
    assert resize_handles.count('"name": "resize_handle"') == 1
    assert "onPositionChanged" not in resize_handles

    router = _router()
    created = router.dispatch({"name": "add_item_slot", "preset_id": "quinta3-compact-blue-strip"})
    root = router.session.page.slots[created.payload["slot_id"]]
    root_id = str(root.metadata["root_node_id"])
    node = router.session.page.node(root_id)
    assert node is not None
    before = len(router.session.history._undo)
    router.session.select(root_id)
    router.session.move_selected(12, 9)
    assert len(router.session.history._undo) == before + 1
    assert router.session.history.undo_label == "Mover elementos"
    moved = node.rect.normalized()
    router.session.resize_node(root_id, x=moved.x, y=moved.y, width=moved.width * 1.1, height=moved.height * 0.9)
    assert len(router.session.history._undo) == before + 2
    assert router.session.history.undo_label == "Redimensionar elemento"


def test_visual_assets_and_anton_are_self_contained_package_data() -> None:
    document = GraphicsDocument(name="Frozen slot assets")
    assert slot_font_family(document) == "Anton"
    assert document.metadata["embedded_fonts"][0]["family"] == "Anton"
    assert Path(document.metadata["embedded_fonts"][0]["extracted_path"]).is_file()

    image_decorations = [
        decoration
        for family in slot_family_entries()
        for decoration in family["INTERNAL_PRESET"].get("metadata", {}).get("decorations", [])
        if decoration.get("kind") == "image"
    ]
    assert image_decorations
    for decoration in image_decorations:
        path = cached_slot_asset_path(decoration["asset_basename"], decoration["asset_sha256"])
        assert path is not None and path.is_file()


@pytest.mark.parametrize(
    "family_id",
    ["quinta3-arched-card", "quinta3-bubble-club", "quinta3-club-side", "quinta3-stationery-round", "quinta3-wood-plaque"],
)
def test_source_visual_layers_are_materialized_and_owned_by_single_slot(family_id: str) -> None:
    router = _router()
    created = router.dispatch({"name": "add_item_slot", "preset_id": family_id})
    slot = router.session.page.slots[created.payload["slot_id"]]
    decorations = [
        router.session.page.node(node_id)
        for node_id in slot.metadata["decorative_nodes"]
        if (router.session.page.node(node_id) is not None and router.session.page.node(node_id).metadata.get("item_slot_decoration"))
    ]
    assert decorations
    root_id = str(slot.metadata["root_node_id"])
    assert all(node is not None and node.id in router.session.page.descendants(root_id) for node in decorations)
    assert all(node.z_index < 20 for node in decorations)


def test_inventory_json_is_stable_json() -> None:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
