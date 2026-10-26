from __future__ import annotations

"""Read-only bridge to the historical SR Studio ImageLibrary.

This never downloads release archives, never changes ImageLibrary's index, and
never promotes unreviewed historical matches to approved images.
"""

from pathlib import Path
import os
import re
import unicodedata


def legacy_image_library_root() -> Path:
    override = os.environ.get("SR_STUDIO_LEGACY_IMAGE_LIBRARY", "").strip()
    if override:
        return Path(override).expanduser()
    # Matches SRStudioProfessional._attach_project(): data_dir / "images".
    return Path.home() / ".srstudio5" / "images"


def _canonical(text: object) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", value.upper()).split())


def _identity(product: dict) -> tuple[str, str, str]:
    return (
        str(product.get("id") or product.get("product_id") or "").strip(),
        str(product.get("ean") or product.get("barcode") or "").strip(),
        _canonical(product.get("display_name") or product.get("name")),
    )


class ApprovedLegacyImageBridge:
    def __init__(self, root: Path | None = None) -> None:
        from srstudio.images.library import ImageLibrary
        self.root = Path(root) if root is not None else legacy_image_library_root()
        self.library = ImageLibrary(self.root)
        self._indexed: dict[str, list] = {}
        self._load()

    def _load(self) -> None:
        for asset in self.library.all(kind="product", status="accepted"):
            if not Path(asset.path).is_file():
                continue
            # A reviewed product photo cannot be matched by filename alone.
            metadata = asset.metadata or {}
            for label, value in (
                ("sku", metadata.get("product_id") or metadata.get("code") or metadata.get("sku")),
                ("ean", metadata.get("ean")),
            ):
                if value:
                    self._indexed.setdefault(f"{label}:{str(value).strip()}", []).append(asset)
            # Exact reviewed product names are allowed only when unique; this
            # also excludes fuzzy lookups and differing package-size suffixes.
            for name in (asset.product_name, asset.product_key):
                key = _canonical(name)
                if key:
                    self._indexed.setdefault(f"name:{key}", []).append(asset)

    def resolve(self, product: dict) -> dict | None:
        sku, ean, name = _identity(product)
        for label, value in (("sku", sku), ("ean", ean), ("name", name)):
            if not value:
                continue
            matches = {asset.id: asset for asset in self._indexed.get(f"{label}:{value}", ())}
            if len(matches) != 1:
                # Ambiguous identities are never resolved by weaker fuzzy scores.
                if len(matches) > 1:
                    return None
                continue
            asset = next(iter(matches.values()))
            # If the product supplies a barcode, a conflicting asset barcode
            # invalidates the match even when its name is identical.
            asset_ean = str((asset.metadata or {}).get("ean") or "").strip()
            if ean and asset_ean and ean != asset_ean:
                return None
            if not Path(asset.path).is_file():
                return None
            return {
                "image_path": str(Path(asset.path).resolve()),
                "image": str(Path(asset.path).resolve()),
                "image_linked_by": "legacy_approved_" + label,
                "image_bank_asset_id": asset.id,
            }
        return None


def enrich_product(product: dict, bridge: ApprovedLegacyImageBridge | None = None) -> dict:
    """Add a safe local legacy image only when the product has no own photo."""
    result = dict(product)
    if result.get("image_path") or result.get("image") or result.get("image_asset_id"):
        return result
    service = bridge if bridge is not None else ApprovedLegacyImageBridge()
    record = service.resolve(result)
    if record:
        result.update(record)
    return result


def enrich_catalog(document, bridge: ApprovedLegacyImageBridge | None = None) -> int:
    """Hydrate catalog thumbnails without altering their SKU, name or price."""
    products = document.metadata.get("products") or []
    if not products:
        return 0
    service = bridge if bridge is not None else ApprovedLegacyImageBridge()
    changed = 0
    for i, product in enumerate(products):
        if not isinstance(product, dict):
            continue
        result = enrich_product(product, service)
        if result != product:
            product.update(result)
            changed += 1
    return changed
