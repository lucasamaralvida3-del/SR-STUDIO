from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from srstudio.images.cloud_publish import ImageBankPublicationBuilder
from srstudio.images.cloud_sync import ImageBankCloudSync
from srstudio.images.library import ImageLibrary


def _png(path: Path, value: int = 130) -> Path:
    Image.new("RGB", (80, 100), (value, 40, 20)).save(path, "PNG")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cloud_sync_downloads_official_asset_and_reuses_cache(tmp_path):
    remote_image = _png(tmp_path / "remote.png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "SR_IMAGE_BANK_1",
                "bank_version": 2,
                "assets": [
                    {
                        "id": "arroz-001",
                        "product_key": "ARROZ VASCONCELOS 5KG",
                        "product_name": "ARROZ VASCONCELOS 5KG",
                        "url": remote_image.as_uri(),
                        "filename": "arroz.png",
                        "sha256": _sha(remote_image),
                        "status": "approved",
                        "preferred": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    library = ImageLibrary(tmp_path / "library")
    sync = ImageBankCloudSync(library, tmp_path / "cloud", manifest_url=manifest.as_uri())

    first = sync.sync()
    assert first.state == "updated"
    assert first.downloaded == 1
    assert library.stats()["accepted"] == 1
    match = library.find_best_for_product("ARROZ VASCONCELOS 5KG")
    assert match is not None
    assert match.asset.source == "cloud"
    assert match.asset.metadata["official"] is True

    second = sync.sync()
    assert second.state == "current"
    assert second.downloaded == 0
    assert second.reused == 1


def test_cloud_sync_never_rejects_personal_assets_when_official_item_is_removed(tmp_path):
    personal = _png(tmp_path / "personal.png", 90)
    library = ImageLibrary(tmp_path / "library")
    local = library.import_image(
        personal,
        product_name="CAFE LOCAL 500G",
        product_key="CAFE LOCAL 500G",
        kind="product",
        review_status="accepted",
        confidence=1.0,
        source_kind="manual",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"format": "SR_IMAGE_BANK_1", "bank_version": 1, "assets": []}),
        encoding="utf-8",
    )
    sync = ImageBankCloudSync(library, tmp_path / "cloud", manifest_url=manifest.as_uri())
    sync.sync()
    assert next(asset for asset in library.all() if asset.id == local.id).review_status == "accepted"


def test_publication_builder_exports_only_approved_product_images(tmp_path):
    library = ImageLibrary(tmp_path / "library")
    approved = _png(tmp_path / "approved.png", 170)
    pending = _png(tmp_path / "pending.png", 80)
    library.import_image(
        approved,
        product_name="LEITE TRIANGULO 1L",
        product_key="LEITE TRIANGULO 1L",
        kind="product",
        review_status="accepted",
        confidence=1.0,
        source_kind="canva",
        preferred=True,
    )
    library.import_image(
        pending,
        product_name="PRODUTO DUVIDOSO",
        product_key="PRODUTO DUVIDOSO",
        kind="product",
        review_status="pending",
        confidence=0.6,
        source_kind="canva",
    )

    result = ImageBankPublicationBuilder(library).build(
        tmp_path / "publish",
        version=7,
        public_base_url="https://images.example.com/sr",
    )
    payload = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert result.assets == 1
    assert payload["bank_version"] == 7
    assert payload["assets"][0]["product_name"] == "LEITE TRIANGULO 1L"
    assert payload["assets"][0]["url"].startswith("https://images.example.com/sr/assets/")
    assert len(list((tmp_path / "publish" / "assets").iterdir())) == 1
