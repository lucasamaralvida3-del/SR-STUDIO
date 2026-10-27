"""Beta59: verified recovery, explicit review and reusable SKU associations."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from srstudio.graphics2 import historical_bank_download as dl
from srstudio.graphics2.image_bank_browser import image_bank_inventory
from srstudio.graphics2.legacy_image_bank_bridge import (
    approved_legacy_image, complete_product_image
)
from srstudio.graphics2.product_image_library import (
    store_product_image, attach_image_to_document
)
from srstudio.graphics2.model import GraphicsDocument
from srstudio.images.library import ImageLibrary


class FakeDownload:
    def __init__(self, data: bytes):
        self.io = BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size):
        return self.io.read(size)


def test_verified_historical_download_only_accepts_pinned_bytes(tmp_path, monkeypatch):
    data = b"beta59 review ZIP stub for transfer verification"
    monkeypatch.setattr(dl, "REVIEW_ARCHIVE_SIZE", len(data))
    monkeypatch.setattr(dl, "REVIEW_ARCHIVE_SHA256", sha256(data).hexdigest())
    archive = tmp_path / "verified.zip"
    result = dl.download_review_archive(
        archive, opener=lambda request, timeout: FakeDownload(data))
    assert result == archive
    assert archive.read_bytes() == data
    with pytest.raises(ValueError, match="não confere"):
        dl.download_review_archive(
            archive, opener=lambda request, timeout: FakeDownload(b"wrong bytes"))
    assert not archive.exists(), "corrupt ZIP must be deleted, not imported"


def test_recovery_imports_review_only_after_integrity_validation(monkeypatch):
    import srstudio.graphics2.historical_review_import as importer
    data = b"fake archive for imported-only-after-hash test"
    monkeypatch.setattr(dl, "REVIEW_ARCHIVE_SIZE", len(data))
    monkeypatch.setattr(dl, "REVIEW_ARCHIVE_SHA256", sha256(data).hexdigest())
    calls = []

    def fake_import(path, *, destination=None):
        assert Path(path).read_bytes() == data
        calls.append(str(path))
        return {"installed_pending": 2, "already_present": 1, "auto_approved": 0}
    monkeypatch.setattr(importer, "import_historical_review_zip", fake_import)
    result = dl.download_and_import_review_bank(
        opener=lambda request, timeout: FakeDownload(data))
    assert len(calls) == 1
    assert result["installed_pending"] == 2
    assert result["auto_approved"] == 0
    assert result["review_only"] is True


def test_pending_photo_is_not_auto_bound_but_manual_confirmation_is_persistent(
        tmp_path, monkeypatch):
    bank = tmp_path / "legacy"
    local = tmp_path / "local"
    photo = tmp_path / "photo.png"
    Image.new("RGB", (110, 150), "#BADA55").save(photo)
    imported = ImageLibrary(bank).import_image(
        photo, kind="product", review_status="pending",
        product_name="AGUA SANITARIA TUFF 5L", product_key="AGUA SANITARIA TUFF 5L")
    monkeypatch.setenv("SR_STUDIO_IMAGE_LIBRARY_ROOT", str(bank))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    product = {"id": "TUFF5L", "name": "AGUA SANITARIA TUFF 5L", "price": "8,79"}
    assert approved_legacy_image(product) is None
    assert not complete_product_image(product).get("image_path")
    inventory = image_bank_inventory()
    candidate = next(a for a in inventory["images"] if a["id"] == imported.id)
    assert candidate["status"] == "pending"
    assert candidate["can_link"] is False  # never automatically accepted
    assert candidate["image_path"] and Path(candidate["image_path"]).exists()

    # The UI asks for explicit manual confirmation after displaying preview.
    saved = store_product_image("TUFF5L", product["name"], candidate["image_path"])
    document = GraphicsDocument()
    document.metadata["products"] = [dict(product)]
    assert attach_image_to_document(document, "TUFF5L", saved)
    assert Path(document.metadata["products"][0]["image_path"]).is_file()
    # The next XLSX import resolves the stored SKU link before any fuzzy guess.
    reimported = complete_product_image(product)
    assert reimported["image_path"] == saved["image_path"]
    assert reimported["image_linked_by"] == "product_id"
    assert ImageLibrary(bank).find_by_id(imported.id).review_status == "pending"


def test_bank_review_is_accessible_inside_products_not_hidden_image_tab():
    root = Path(__file__).resolve().parents[1] / "src/srstudio/graphics2"
    qml = (root / "qml/GraphicsEditor.qml").read_text("utf-8")
    host = (root / "qt_host.py").read_text("utf-8")
    assert 'visible: studioSection === 0 && showProductImageReview' in qml
    assert 'visible: studioSection === 0 && !showProductImageReview' in qml
    assert 'text: "Banco SR"' in qml
    assert "downloadHistoricalReviewBank()" in qml
    assert "historicalReviewZipDialog.open()" in qml
    assert "bankReviewConfirm.open()" in qml
    assert "sceneBridge.attachProductImage(" in qml
    assert "imageBankTargetProductId" in qml
    assert "function bankSuggestionScore(entry)" in qml
    assert "def downloadHistoricalReviewBank(self)" in host
    assert '"title":"Imagens"' not in qml
