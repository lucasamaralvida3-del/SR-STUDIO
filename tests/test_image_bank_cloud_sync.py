from __future__ import annotations

import hashlib
import json
import zipfile
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
    assert Path(result.base_bundle_path).is_file()
    assert payload["base_bundle"]["sha256"] == _sha(Path(result.base_bundle_path))
    with zipfile.ZipFile(result.base_bundle_path) as archive:
        assert len([name for name in archive.namelist() if name.startswith("assets/")]) == 1


def test_first_sync_can_seed_from_verified_base_bundle_without_individual_downloads(tmp_path):
    remote_image = _png(tmp_path / "seed.png", 190)
    asset_id = "leite-001"
    bundle = tmp_path / "base-v3.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(remote_image, f"assets/{asset_id}.png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format": "SR_IMAGE_BANK_1",
                "bank_version": 3,
                "base_bundle": {"version": 3, "url": bundle.as_uri(), "sha256": _sha(bundle)},
                "assets": [
                    {
                        "id": asset_id,
                        "product_name": "LEITE TRIANGULO 1L",
                        "product_key": "LEITE TRIANGULO 1L",
                        "filename": f"{asset_id}.png",
                        "url": "file:///this/path/must/not/be-needed.png",
                        "sha256": _sha(remote_image),
                        "status": "approved",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    library = ImageLibrary(tmp_path / "library")
    sync = ImageBankCloudSync(library, tmp_path / "cloud", manifest_url=manifest.as_uri())
    result = sync.sync()
    assert result.state == "updated"
    assert result.downloaded == 0
    assert result.reused == 1
    assert "Pacote-base instalado" in result.details
    assert library.find_best_for_product("LEITE TRIANGULO 1L") is not None


def test_bootstrap_manifest_can_redirect_clients_to_future_https_endpoint(tmp_path, monkeypatch):
    library = ImageLibrary(tmp_path / "library")
    sync = ImageBankCloudSync(library, tmp_path / "cloud", manifest_url="https://bootstrap.example/manifest.json")
    payloads = {
        "https://bootstrap.example/manifest.json": {"redirect_manifest_url": "https://cdn.example/sr/manifest.json"},
        "https://cdn.example/sr/manifest.json": {"format": "SR_IMAGE_BANK_1", "bank_version": 9, "assets": []},
    }
    monkeypatch.setattr(sync, "_fetch_json", lambda url: dict(payloads[url]))
    result = sync.sync()
    assert result.state == "updated"
    assert result.remote_version == 9
    assert sync.local_version() == 9
