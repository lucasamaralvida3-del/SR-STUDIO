from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession


REQUIRED_FAMILIES = {
    "quinta3-meat-strip",
    "quinta3-wood-plaque",
    "quinta3-compact-promo",
    "quinta3-club-side",
    "quinta3-stationery-round",
}

EXAMPLES = [
    (
        "quinta3-meat-strip",
        "costela",
        {"id": "costela", "name": "COSTELA GAÚCHA", "price": "26,99", "unit": "KG"},
    ),
    (
        "quinta3-wood-plaque",
        "extra",
        {
            "id": "extra",
            "name": "EXTRA TOM PREDILECTA CEBOLA ALHO 300G",
            "price": "1,79",
            "secondary_price": "1,49",
            "unit": "UN",
            "secondary_unit": "UN",
            "promotion_label": "PROMOÇÃO",
            "club_label": "NO SR CLUBE SMART",
        },
    ),
    (
        "quinta3-compact-promo",
        "odor-boom",
        {
            "id": "odor-boom",
            "name": "ODOR BOOM PERFUME EM CRISTAIS 275G",
            "price": "19,43",
            "secondary_price": "16,99",
            "unit": "UN",
            "secondary_unit": "UN",
            "image_asset_id": "asset-odor-boom",
        },
    ),
    (
        "quinta3-club-side",
        "amaciante",
        {
            "id": "amaciante",
            "name": "AMACIANTE VIDA MACIA 1L",
            "price": "10,99",
            "secondary_price": "11,99",
            "unit": "CADA",
            "secondary_unit": "CADA",
        },
    ),
    (
        "quinta3-stationery-round",
        "cadernos",
        {
            "id": "cadernos",
            "name": "CADERNOS TURMA DA BELA BROCHURA 80F",
            "price": "9,00",
            "unit": "UN",
            "image_asset_id": "asset-cadernos",
        },
    ),
]


def _router(document: GraphicsDocument | None = None) -> ItemSlotCommandRouter:
    return ItemSlotCommandRouter(GraphicsSession(document or GraphicsDocument(name="Quinta3 manual Studio test")))


def test_real_studio_payload_exposes_exactly_five_certified_quinta3_families() -> None:
    router = _router()
    payload = router.payload()
    preset_ids = {str(item.get("id") or "") for item in payload["editor"]["item_slot_presets"]}
    quinta_ids = {item for item in preset_ids if item.startswith("quinta3-")}
    assert quinta_ids == REQUIRED_FAMILIES


@pytest.mark.parametrize(("family_id", "profile_id", "product"), EXAMPLES)
def test_real_studio_create_and_apply_product_uses_certified_family_runtime(
    family_id: str,
    profile_id: str,
    product: dict[str, str],
) -> None:
    router = _router()
    created = router.dispatch({"name": "add_item_slot", "preset_id": family_id})
    assert created.ok and created.changed
    slot_id = str(created.payload["slot_id"])
    slot = router.session.page.slots[slot_id]
    assert slot.metadata["preset_id"] == family_id
    assert slot.metadata["quinta3_family"] == family_id

    bound_product = dict(product)
    bound_product["quinta3_supervised_profile"] = profile_id
    bound = router.dispatch({"name": "bind_product", "slot_id": slot_id, "product": bound_product})
    assert bound.ok and bound.changed

    slot = router.session.page.slots[slot_id]
    assert slot.metadata["supervised_profile"] == profile_id
    assert router.session.page.node(slot.node_by_role[BindingRole.NAME.value]).text == product["name"]
    assert router.session.page.node(slot.node_by_role[BindingRole.UNIT.value]).text == product["unit"]

    if product.get("image_asset_id"):
        primary_image = router.session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
        assert primary_image.asset_id == product["image_asset_id"]
        extras = slot.metadata.get("extra_bindings") or {}
        for node_id in extras.get(BindingRole.IMAGE.value, []):
            assert router.session.page.node(node_id).asset_id == product["image_asset_id"]

    extras = slot.metadata.get("extra_bindings") or {}
    if slot.metadata.get("secondary_price_visible"):
        assert extras.get("app_price_currency")
        assert extras.get("app_price_integer")
        assert extras.get("app_price_cents")
        assert extras.get("app_unit")
    if slot.metadata.get("promotion_visible"):
        assert router.session.page.node(extras["promotion"][0]).text == product.get("promotion_label", "PROMOÇÃO")
    if slot.metadata.get("club_visible"):
        assert router.session.page.node(extras["club_label"][0]).text == product.get("club_label", "NO SR CLUBE SMART")


def test_studio_save_reopen_preserves_five_presets_and_created_family_state() -> None:
    router = _router()
    created_ids: list[str] = []
    for family_id in sorted(REQUIRED_FAMILIES):
        result = router.dispatch({"name": "add_item_slot", "preset_id": family_id})
        assert result.ok and result.changed
        created_ids.append(str(result.payload["slot_id"]))

    reopened = GraphicsDocument.from_dict(router.session.document.to_dict())
    reopened_router = _router(reopened)
    payload = reopened_router.payload()
    preset_ids = {str(item.get("id") or "") for item in payload["editor"]["item_slot_presets"]}
    assert REQUIRED_FAMILIES <= preset_ids
    for slot_id in created_ids:
        slot = reopened.active_page.slots[slot_id]
        assert slot.metadata["preset_id"] in REQUIRED_FAMILIES
        assert slot.metadata["quinta3_family"] == slot.metadata["preset_id"]
        assert slot.metadata.get("source_supervised_geometry") is True


def test_project_actions_qml_consumes_backend_item_slot_presets_without_ui_fork() -> None:
    qml = Path("src/srstudio/graphics2/qml/ProjectActions.qml").read_text(encoding="utf-8")
    assert "scene.editor.item_slot_presets" in qml
    assert '"add_item_slot"' in qml
    assert "itemSlotPresets()" in qml
    assert "Repeater" in qml
