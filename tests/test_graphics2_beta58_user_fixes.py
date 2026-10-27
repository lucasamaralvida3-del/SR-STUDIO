"""SR Beta58: promotion glyphs, campaign dates and spreadsheet-only photo linking."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from srstudio.graphics2 import product_data_runtime
from srstudio.graphics2.campaign_tools import DATE_PLACEMENTS, set_campaign_date
from srstudio.graphics2.item_slots import (
    bind_product_to_item_slot, create_item_slot, duplicate_item_slot,
    set_reference_price_mode,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession


@pytest.mark.parametrize("preset", ("individual-beta44", "multi-cell-beta44"))
@pytest.mark.parametrize("retail", ("3,99", "32,86", "131,99"))
def test_promotion_badge_keeps_split_price_in_sync_with_its_original_binding(preset, retail):
    session = GraphicsSession(GraphicsDocument())
    if preset == "multi-cell-beta44":
        strip = create_multi_item_strip(session, count=5, price_mode="two")
        slot = session.page.slots[strip["slot_ids"][0]]
    else:
        slot = create_item_slot(session, preset)
    product = {"id": "OMO", "name": "SABÃO EM PÓ OMO 2,2KG",
               "price": retail, "club_price": "2,89", "unit": "UN"}
    assert bind_product_to_item_slot(session, slot.id, product)
    page = session.page
    bound = page.node(slot.node_by_role[BindingRole.RETAIL_PRICE.value])
    assert bound.text == "R$ " + retail
    assert not bound.visible  # original remains editable but not double-painted
    components = {key: page.node(node_id)
                  for key, node_id in slot.metadata["promotion_amount_nodes"].items()}
    assert {key: node.text for key, node in components.items()} == {
        "promo_currency": "R$", "promo_integer": retail.split(",")[0],
        "promo_cents": "," + retail.split(",")[1]}
    assert all(node.visible for node in components.values())
    assert components["promo_integer"].style["align"] == "right"
    assert components["promo_cents"].style["align"] == "left"
    assert components["promo_currency"].rect.right <= components["promo_integer"].rect.x
    assert components["promo_integer"].rect.right <= components["promo_cents"].rect.x
    assert components["promo_cents"].rect.right <= page.node(
        slot.metadata["promotion_unit_node_id"]).rect.x
    assert page.node(slot.metadata["promotion_unit_node_id"]).text == "UN"
    assert set_reference_price_mode(session, [slot.id], "one")
    assert all(not page.node(node.id).visible for node in components.values())
    assert set_reference_price_mode(session, [slot.id], "two")
    assert all(page.node(node.id).visible for node in components.values())


def test_promotion_price_nodes_duplicate_with_own_ids():
    session = GraphicsSession(GraphicsDocument())
    slot = create_item_slot(session, "individual-beta44")
    assert bind_product_to_item_slot(session, slot.id, {
        "id": "123", "name": "Arroz", "price": "32,86",
        "club_price": "31,99", "unit": "UN"})
    clone = duplicate_item_slot(session, slot.id, include_product=True)
    for key, node_id in slot.metadata["promotion_amount_nodes"].items():
        clone_id = clone.metadata["promotion_amount_nodes"][key]
        assert node_id != clone_id
        assert session.page.node(clone_id).text == session.page.node(node_id).text


@pytest.mark.parametrize("campaign", sorted(DATE_PLACEMENTS))
def test_date_is_auto_refitted_inside_campaign_pill(campaign):
    session = GraphicsSession(GraphicsDocument())
    session.page.metadata["campaign_id"] = campaign
    set_campaign_date(session, mode="manual", value="28/10/2026")
    node = session.page.node(session.page.metadata["campaign_date_node"])
    assert node.style["font_size"] <= 13
    assert node.style["fit_inside_box"] is True
    assert node.style["single_line"] is True
    assert node.metadata["campaign_date_box_version"] >= 58
    x, y, w, h = DATE_PLACEMENTS[campaign]
    assert node.transform.x == pytest.approx(session.page.width * x)
    assert node.transform.y == pytest.approx(session.page.height * y)
    assert node.transform.width == pytest.approx(session.page.width * w)
    assert node.transform.height == pytest.approx(session.page.height * h)
    # Reset an incorrect saved position on the next date/campaign update.
    node.transform.y += 120
    set_campaign_date(session, mode="manual", value="27/10/2026")
    assert node.transform.y == pytest.approx(session.page.height * y)


def test_spreadsheet_import_hydrates_only_imported_items(tmp_path, monkeypatch):
    photo = tmp_path / "sku.jpg"
    photo.write_bytes(b"picture-placeholder")
    sheet = tmp_path / "ofertas.xlsx"
    sheet.write_bytes(b"fake-excel")
    session = GraphicsSession(GraphicsDocument())
    class FakeService:
        def import_file(self, path, *, project_name=""):
            doc = GraphicsDocument()
            doc.metadata["products"] = [
                {"id": "SKU1", "name": "Sabão em pó 2kg", "price": "32,86"},
                {"id": "SKU2", "name": "Detergente 500ml", "price": "2,47"},
            ]
            return SimpleNamespace(document=doc)
    monkeypatch.setattr(product_data_runtime.import_bridge, "GraphicsImportService", FakeService)
    import srstudio.graphics2.legacy_image_bank_bridge as bank
    def approved_only(p, *, root=None, manual_links=None):
        product = dict(p)
        if p["id"] == "SKU1":
            product.update({"image_path": str(photo), "image": str(photo),
                            "image_linked_by": "approved_legacy_ean"})
        return product
    monkeypatch.setattr(bank, "complete_product_image", approved_only)
    monkeypatch.setattr("srstudio.graphics2.product_image_library.read_product_links",
                        lambda: {})
    result = session.import_product_catalog(str(sheet))
    assert result["images_linked"] == 1
    assert result["images_missing"] == 1
    assert session.document.metadata["products"][0]["image_path"] == str(photo)
    assert not session.document.metadata["products"][1].get("image_path")


def test_products_panel_is_wider_but_remains_resizable_and_remembers_size():
    root = Path(__file__).resolve().parents[1] / "src/srstudio/graphics2"
    qml = (root / "qml/GraphicsEditor.qml").read_text("utf-8")
    host = (root / "qt_host.py").read_text("utf-8")
    assert "SplitView.maximumWidth: 565" in qml
    assert "productSidebarWidth: sceneBridge.productSidebarWidth" in qml
    assert "Layout.preferredWidth: 84" in qml
    assert "Layout.preferredHeight: 96" in qml
    assert "saveProductSidebarWidth" in qml and "QSettings" in host
    assert "refreshProductImages()" in qml
    assert "Fotos encontradas:" in qml
