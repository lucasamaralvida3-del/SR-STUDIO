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
