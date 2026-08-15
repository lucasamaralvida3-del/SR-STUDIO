from pathlib import Path

from PIL import Image

from srstudio.core.models import Product
from srstudio.images.library import ImageLibrary
from srstudio.importers.pipeline import ImportSummary, UnifiedImportPipeline


def _image(path: Path) -> Path:
    Image.new("RGB", (180, 240), (90, 120, 150)).save(path, "PNG")
    return path


def test_pending_image_is_not_used_automatically(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    source = _image(tmp_path / "produto.png")
    asset = library.learn_product_image(source, "ARROZ VASCONCELOS 5KG", confidence=0.70)
    assert asset.review_status == "pending"

    product = Product(original_name="ARROZ VASCONCELOS 5KG")
    summary = ImportSummary("teste.xlsx")
    pipeline = UnifiedImportPipeline(image_library=library)
    pipeline._attach_learned_image(product, summary)

    assert product.image_path == ""
    assert summary.images_matched == 0


def test_approved_image_can_be_used_automatically(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    source = _image(tmp_path / "produto.png")
    asset = library.learn_product_image(source, "ARROZ VASCONCELOS 5KG", confidence=0.70)
    library.set_review_status(asset.id, "accepted")

    product = Product(original_name="ARROZ VASCONCELOS 5KG")
    summary = ImportSummary("teste.xlsx")
    pipeline = UnifiedImportPipeline(image_library=library)
    pipeline._attach_learned_image(product, summary)

    assert product.image_path == asset.path
    assert product.metadata["image_bank_asset_id"] == asset.id
    assert summary.images_matched == 1


def test_same_image_seen_on_different_products_is_forced_back_to_review(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    source = _image(tmp_path / "produto.png")

    first = library.learn_product_image(source, "ARROZ VASCONCELOS 5KG", confidence=0.99)
    assert first.review_status == "accepted"

    second = library.learn_product_image(source, "FEIJAO VASCONCELOS 1KG", confidence=0.99)
    assert second.id == first.id
    assert second.review_status == "pending"
    assert second.preferred is False
    assert second.metadata["review_reason"] == "same_image_multiple_products"
    assert set(second.metadata["conflicting_product_names"]) == {
        "ARROZ VASCONCELOS 5KG",
        "FEIJAO VASCONCELOS 1KG",
    }

    assert library.find_best_for_product("ARROZ VASCONCELOS 5KG") is None
    assert library.find_best_for_product("FEIJAO VASCONCELOS 1KG") is None


def test_approving_cross_product_conflict_keeps_only_current_product_association(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    source = _image(tmp_path / "produto.png")
    first = library.learn_product_image(source, "ARROZ VASCONCELOS 5KG", confidence=0.99)
    conflict = library.learn_product_image(source, "FEIJAO VASCONCELOS 1KG", confidence=0.99)
    assert conflict.review_status == "pending"

    approved = library.set_review_status(first.id, "accepted")
    assert approved.review_status == "accepted"
    assert approved.metadata.get("review_reason") is None
    assert "FEIJAO VASCONCELOS 1KG" not in approved.aliases
    assert library.find_best_for_product("ARROZ VASCONCELOS 5KG") is not None
    assert library.find_best_for_product("FEIJAO VASCONCELOS 1KG") is None
