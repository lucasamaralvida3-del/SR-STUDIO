from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .library import ImageAsset, ImageLibrary


@dataclass(frozen=True, slots=True)
class PublicationResult:
    version: int
    assets: int
    output_dir: str
    manifest_path: str
    base_bundle_path: str
    bytes_total: int


class ImageBankPublicationBuilder:
    """Build an upload-ready official SR Image Bank package from approved local assets."""

    def __init__(self, library: ImageLibrary) -> None:
        self.library = library

    def build(
        self,
        output_dir: str | Path,
        *,
        version: int,
        public_base_url: str,
    ) -> PublicationResult:
        if version < 1:
            raise ValueError("A versão do Banco SR deve ser maior que zero.")
        base_url = public_base_url.rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("A URL pública do Banco SR deve começar com http:// ou https://.")

        root = Path(output_dir)
        assets_dir = root / "assets"
        if root.exists():
            shutil.rmtree(root)
        assets_dir.mkdir(parents=True, exist_ok=True)

        manifest_assets: list[dict] = []
        bytes_total = 0
        approved = [
            asset
            for asset in self.library.all(kind="product", status="accepted")
            if Path(asset.path).is_file()
        ]
        for asset in sorted(approved, key=lambda item: (item.product_key, item.id)):
            source = Path(asset.path)
            suffix = source.suffix.lower() or ".webp"
            cloud_id = self._cloud_id(asset)
            filename = f"{cloud_id}{suffix}"
            destination = assets_dir / filename
            shutil.copy2(source, destination)
            sha256 = self._sha256(destination)
            size = destination.stat().st_size
            bytes_total += size
            manifest_assets.append(
                {
                    "id": cloud_id,
                    "product_key": asset.product_key,
                    "product_name": asset.product_name or asset.original_name,
                    "aliases": list(asset.aliases),
                    "tags": sorted(set((*asset.tags, "oficial", "cloud"))),
                    "ean": str(asset.metadata.get("ean") or ""),
                    "category": str(asset.metadata.get("category") or ""),
                    "preferred": bool(asset.preferred),
                    "status": "approved",
                    "version": int(asset.metadata.get("cloud_version", 1) or 1),
                    "filename": filename,
                    "url": f"{base_url}/assets/{filename}",
                    "sha256": sha256,
                    "size": size,
                    "width": asset.width,
                    "height": asset.height,
                }
            )

        bundle_name = f"base-v{version}.zip"
        bundle_path = root / bundle_name
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(assets_dir.iterdir()):
                if path.is_file():
                    archive.write(path, f"assets/{path.name}")
        bundle_sha = self._sha256(bundle_path)
        bundle_size = bundle_path.stat().st_size

        manifest = {
            "format": "SR_IMAGE_BANK_1",
            "bank_version": version,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "base_version": version,
            "asset_count": len(manifest_assets),
            "base_bundle": {
                "version": version,
                "url": f"{base_url}/{bundle_name}",
                "sha256": bundle_sha,
                "size": bundle_size,
            },
            "assets": manifest_assets,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return PublicationResult(
            version=version,
            assets=len(manifest_assets),
            output_dir=str(root),
            manifest_path=str(manifest_path),
            base_bundle_path=str(bundle_path),
            bytes_total=bytes_total + bundle_size,
        )

    @staticmethod
    def _cloud_id(asset: ImageAsset) -> str:
        existing = str(asset.metadata.get("cloud_asset_id") or "").strip()
        if existing:
            return existing
        basis = f"{asset.product_key}|{asset.id}".encode("utf-8")
        return hashlib.sha256(basis).hexdigest()[:24]

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()
