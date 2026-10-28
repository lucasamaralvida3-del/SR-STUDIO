from srstudio.graphics2.image_suggestions import (
    score_image_candidate, suggest_product_images, image_review_states,
    approved_link_compatible,
)
from srstudio.graphics2.product_image_library import store_product_images_batch, read_product_links
from srstudio.graphics2.product_image_library import store_product_image, apply_stored_product_links
from srstudio.graphics2.legacy_image_bank_bridge import complete_product_image
from srstudio.graphics2.model import GraphicsDocument
from PIL import Image
import pytest


def test_identifier_priority_and_package_safety():
    product = {"id": "SKU-18", "ean": "7891234567895", "name": "CAFÉ DO SOL 500G", "brand": "DO SOL"}
    candidates = [
        {"id": "wrong-size", "kind": "product", "ean": "7891234567895", "name": "CAFÉ DO SOL 1KG"},
        {"id": "wrong-ean", "kind": "product", "ean": "7890000000000", "name": "CAFÉ DO SOL 500G"},
        {"id": "exact", "kind": "product", "ean": "7891234567895", "name": "CAFÉ DO SOL 500G"},
        {"id": "description", "kind": "product", "name": "CAFÉ DO SOL 500G"},
    ]
    suggestions = suggest_product_images(product, candidates)
    assert [item["id"] for item in suggestions] == ["exact", "description"]
    assert suggestions[0]["reason"] == "EAN/GTIN correspondente"
    assert all(item["requires_confirmation"] for item in suggestions)


def test_distinct_internal_codes_and_brand_are_never_suggested():
    product = {"id": "42", "name": "LEITE BOM 1L", "brand": "BOM"}
    assert score_image_candidate(product, {"kind": "product", "product_id": "43",
                                           "name": "LEITE BOM 1L"})["score"] == 0
    assert score_image_candidate(product, {"kind": "product", "name": "LEITE BOM 1L",
                                           "brand": "OUTRA"})["score"] == 0


def test_batch_requires_explicit_list_and_validates_all_before_saving(tmp_path):
    photo = tmp_path / "real.png"
    Image.new("RGB", (20, 20), "red").save(photo)
    invalid = tmp_path / "broken.png"
    invalid.write_text("not an image")
    requests = [{"product_id": "A", "name": "Produto A", "image_path": str(photo)},
                {"product_id": "B", "name": "Produto B", "image_path": str(invalid)}]
    with pytest.raises(Exception):
        store_product_images_batch(requests, root=tmp_path / "library")
    assert read_product_links(root=tmp_path / "library") == {}
    requests.pop()
    assert store_product_images_batch(requests, root=tmp_path / "library")[0]["product_id"] == "A"


def test_review_states_distinguish_linked_pending_and_unavailable():
    products = [{"id": "A", "name": "CAFE BOM 500G", "image_path": "already-linked.png"},
                {"id": "B", "name": "CAFE BOM 500G"},
                {"id": "C", "name": "ARROZ NOVO 5KG"}]
    images = [{"id": "photo", "kind": "product", "name": "CAFE BOM 500G"}]
    assert image_review_states(products, images) == {
        "A": "linked", "B": "pending", "C": "missing",
    }


def test_reused_sku_requires_compatible_product_description_and_pack():
    link = {"name": "CAFÉ BOM 500G"}
    assert approved_link_compatible({"name": "CAFÉ BOM 500G EXTRA FORTE"}, link)
    assert not approved_link_compatible({"name": "CAFÉ BOM 1KG"}, link)
    assert not approved_link_compatible({"name": "ARROZ BRANCO 500G"}, link)


def test_wrong_pack_with_reused_sku_does_not_auto_link(tmp_path):
    photo = tmp_path / "cafe.png"
    Image.new("RGB", (20, 20), "brown").save(photo)
    link = store_product_image("SKU-1", "CAFÉ BOM 500G", str(photo), root=tmp_path / "bank")
    changed = {"id": "SKU-1", "name": "CAFÉ BOM 1KG"}
    assert "image_path" not in complete_product_image(changed, manual_links={"SKU-1": link},
                                                       root=tmp_path / "missing-legacy")
    document = GraphicsDocument()
    document.metadata["products"] = [changed]
    assert apply_stored_product_links(document, root=tmp_path / "bank") == 0
