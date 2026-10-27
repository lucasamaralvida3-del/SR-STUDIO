from __future__ import annotations

"""Conservative read-only bridge from the legacy SR ImageLibrary to G2.

Never use fuzzy matches to auto-place packaging in a supermarket flyer.
A manual G2 image always wins. Unapproved historical corpus images must be
reviewed in the existing SR image-bank tools before they become eligible.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any
import os
import re


def image_bank_root() -> Path:
    configured = os.environ.get("SR_STUDIO_IMAGE_LIBRARY_ROOT", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".srstudio5" / "images"


def _identifier(value: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper().strip())


def _name(value: Any) -> str:
    from srstudio.images.association import normalize_product_name
    return normalize_product_name(str(value or ""))


@lru_cache(maxsize=12)
def _approved_assets(path: str, stamp: tuple[int, ...]):
    from srstudio.images.library import ImageLibrary
    # The official SR Studio shell stores the original ImageLibrary index
    # under ~/.srstudio5/images. Do not duplicate or migrate that database.
    library = ImageLibrary(path)
    return tuple(
        asset for asset in library.all(kind="product", status="accepted")
        if not asset.metadata.get("official") or asset.metadata.get("official_active", True)
    )


def _verified_assets(root: Path):
    index = root / "index.json"
    if not index.is_file():
        return ()
    try:
        stat = index.stat()
        # ImageLibrary replaces the index atomically. Include file identity:
        # accepted/rejected have equal length and Windows may preserve mtime.
        return _approved_assets(str(root.resolve()), (stat.st_mtime_ns, stat.st_size, stat.st_ino))
    except (OSError, ValueError):
        return ()


def approved_legacy_image(product: dict[str, Any], *, root: Path | None = None) -> dict[str, str] | None:
    """Return a unique vetted file, never an unreviewed or approximate guess.

    Ranking is identifier first (code/EAN), then exact normalized full name.
    Different matching images are ambiguous unless one is explicitly marked
    preferred by the human image-bank editor.
    """
    bank = Path(root) if root is not None else image_bank_root()
    codes = {
        _identifier(product.get(field))
        for field in ("id", "product_id", "code", "sku")
        if product.get(field) not in (None, "")
    }
    eans = {
        _identifier(product.get(field))
        for field in ("ean", "barcode", "cod_barras")
        if product.get(field) not in (None, "")
    }
    names = {
        _name(product.get(field))
        for field in ("name", "display_name", "original_name")
        if product.get(field)
    }
    codes.discard("")
    eans.discard("")
    names.discard("")
    assets = [
        asset for asset in _verified_assets(bank)
        if Path(asset.path).is_file() and asset.review_status == "accepted"
    ]
    if not assets:
        return None

    def select(candidates, method):
        # A duplicated file is harmless, competing different photographs are
        # not. Product identity may never be guessed from a nearest match.
        unique = {str(Path(a.path).resolve()): a for a in candidates}
        if not unique:
            return None
        if len(unique) > 1:
            preferred = [a for a in unique.values() if a.preferred]
            if len(preferred) != 1:
                return None
            chosen = preferred[0]
        else:
            chosen = next(iter(unique.values()))
        return {
            "image_path": str(Path(chosen.path).resolve()),
            "image": str(Path(chosen.path).resolve()),
            "image_linked_by": "approved_legacy_" + method,
            "image_bank_asset_id": chosen.id,
        }

    # Code and barcode are different namespaces: never treat a numerical
    # barcode as an SKU unless the asset explicitly records it as such.
    for method, wanted, fields in (
        ("ean", eans, ("ean", "barcode", "cod_barras")),
        ("code", codes, ("code", "product_code", "sku", "product_id")),
    ):
        if wanted:
            choices = [
                asset for asset in assets
                if any(_identifier(asset.metadata.get(field)) in wanted
                       for field in fields if asset.metadata.get(field))
            ]
            picked = select(choices, method)
            if picked is not None:
                return picked
            if choices:
                return None  # Explicit but ambiguous identity blocks guessing.

    if not names:
        return None
    candidates = [
        asset for asset in assets
        if _name(asset.product_name or asset.product_key) in names
        or _name(asset.product_key) in names
    ]
    return select(candidates, "exact_name")


def complete_product_image(product: dict[str, Any], *,
                           root: Path | None = None,
                           manual_links: dict[str, dict] | None = None) -> dict[str, Any]:
    """Add an image only when the product lacks a usable existing one."""
    payload = dict(product)
    current = str(payload.get("image_path") or payload.get("image") or "").strip()
    if current:
        try:
            if Path(current).is_file() or current.startswith(("https://", "http://")):
                return payload
        except (OSError, ValueError):
            pass

    from .product_image_library import read_product_links
    if manual_links is None:
        manual_links = read_product_links()
    key = str(payload.get("id") or payload.get("product_id") or "").strip()
    manual = manual_links.get(key)
    if manual and Path(str(manual.get("image_path") or "")).is_file():
        payload.update({
            "image_path": manual["image_path"],
            "image": manual["image_path"],
            "image_linked_by": "product_id",
        })
        return payload
    match = approved_legacy_image(payload, root=root)
    if match is not None:
        payload.update(match)
    return payload


def hydrate_legacy_bank(document, *, root: Path | None = None) -> int:
    """Fill only missing catalog images; no thumbnail or label overwritten."""
    products = document.metadata.get("products") or []
    from .product_image_library import read_product_links
    manual = read_product_links()
    changed = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        resolved = complete_product_image(product, root=root, manual_links=manual)
        if resolved != product:
            product.update(resolved)
            changed += 1
    return changed
