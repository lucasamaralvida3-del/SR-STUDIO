"""The Images sidebar must show the real SR bank, not duplicate Produtos."""

from pathlib import Path

from PIL import Image

from srstudio.graphics2.image_bank_browser import image_bank_inventory
from srstudio.graphics2.product_image_library import store_product_image
from srstudio.images.library import ImageLibrary


def _image(path: Path, color: str) -> Path:
    Image.new("RGB", (36, 48), color).save(path)
    return path


def test_inventory_shows_manual_approved_and_review_without_linking(tmp_path):
    legacy = tmp_path / "legacy"
    catalog = tmp_path / "catalog"
    bank = ImageLibrary(legacy)
    accepted = bank.import_image(
        _image(tmp_path / "arroz.png", "blue"), product_name="ARROZ 5KG",
        product_key="ARROZ 5KG", kind="product", review_status="accepted",
        source_kind="manual-review")
    pending = bank.import_image(
        _image(tmp_path / "unreviewed.png", "red"), kind="unknown",
        review_status="pending", source_kind="legacy-github-corpus")
    rejected = bank.import_image(
        _image(tmp_path / "rejected.png", "green"), kind="product",
        review_status="rejected")
    manual = store_product_image("123", "ARROZ 5KG",
                                 str(tmp_path / "arroz.png"), root=catalog)
    result = image_bank_inventory(legacy_root=legacy, products_root=catalog)
    images = {item["id"]: item for item in result["images"]}
    assert result["counts"] == {
        "approved": 1, "pending": 1, "rejected": 1,
        "manual": 1, "missing_files": 0,
    }
    assert images[accepted.id]["can_link"] is True
    assert images[pending.id]["can_link"] is False
    assert images[pending.id]["status"] == "pending"
    assert rejected.id not in images
    assert images["product:123"]["status"] == "manual"
    assert images["product:123"]["image_path"] == manual["image_path"]
    assert bank.all(status="pending")[0].id == pending.id  # read-only
    assert bank.all(status="accepted")[0].id == accepted.id


def test_uninstalled_historic_archive_does_not_pretend_images_exist(tmp_path):
    result = image_bank_inventory(legacy_root=tmp_path / "none",
                                  products_root=tmp_path / "empty")
    assert not result["images"]
    assert result["counts"]["approved"] == 0
    assert "revisadas" in result["historical_review_note"]
    assert not (tmp_path / "none" / "index.json").exists()


def test_broken_file_is_counted_without_rendering_missing_thumbnail(tmp_path):
    bank = ImageLibrary(tmp_path / "legacy")
    path = _image(tmp_path / "gone.png", "yellow")
    record = bank.import_image(path, kind="product", review_status="accepted")
    Path(record.path).unlink()
    data = image_bank_inventory(legacy_root=tmp_path / "legacy",
                                products_root=tmp_path / "manual")
    assert data["counts"]["approved"] == 1
    assert data["counts"]["missing_files"] == 1
    assert not data["images"]


def test_qml_images_has_independent_real_bank_gallery():
    qml = (Path(__file__).parents[1] / "src" / "srstudio" / "graphics2"
           / "qml" / "GraphicsEditor.qml").read_text(encoding="utf-8")
    assert "visible: studioSection === 0 || studioSection === 3" not in qml
    assert "sceneBridge.imageBankJson()" in qml
    assert "filteredBankImages()" in qml
    assert "sceneBridge.openImageBankFolder()" in qml
    assert 'text: "Usar neste produto"' in qml
    assert 'enabled: !!modelData.can_link && !!imageBankTargetProductId' in qml
