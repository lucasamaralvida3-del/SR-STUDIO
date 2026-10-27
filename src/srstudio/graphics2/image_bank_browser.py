from __future__ import annotations

"""Read-only, explicit gallery of local SR Studio image banks for Graphics2.

A historic recovery is not an approved product photo. The editor may display
review candidates with a warning, but cannot silently bind them by SKU/name.
This inventory never moves files, changes review status or creates associations.
"""

from pathlib import Path
from typing import Any


def image_bank_inventory(*, legacy_root: Path | None = None,
                         products_root: Path | None = None) -> dict[str, Any]:
    from .legacy_image_bank_bridge import image_bank_root
    from .product_image_library import library_root, read_product_links

    legacy = Path(legacy_root) if legacy_root is not None else image_bank_root()
    products = Path(products_root) if products_root is not None else library_root()
    counts = {"approved": 0, "pending": 0, "rejected": 0, "manual": 0, "missing_files": 0}
    images: list[dict[str, Any]] = []

    if (legacy / "index.json").is_file():
        from srstudio.images.library import ImageLibrary
        for asset in ImageLibrary(legacy).all():
            state = str(asset.review_status or "pending")
            if state not in {"accepted", "pending", "rejected"}:
                state = "pending"
            if state == "accepted":
                counts["approved"] += 1
            else:
                counts[state] += 1
            path = Path(asset.path)
            if not path.is_file():
                counts["missing_files"] += 1
                continue
            if state == "rejected":
                continue
            images.append({
                "id": str(asset.id), "name": (asset.product_name or asset.product_key
                    or asset.metadata.get("review_original_filename")
                    or asset.source_file or asset.original_name or "Imagem sem identificação"),
                "image_path": str(path.resolve()), "source": "Banco SR",
                "status": "approved" if state == "accepted" else "pending",
                "can_link": (state == "accepted" and asset.kind == "product"
                             and (not asset.metadata.get("official")
                                  or asset.metadata.get("official_active", True))),
                "product_id": "",
                "kind": str(asset.kind),
            })

    # Product-specific local links are already manually associated by SKU.
    for key, item in sorted(read_product_links(root=products).items()):
        path = Path(str(item["image_path"]))
        if not path.is_file():
            continue
        counts["manual"] += 1
        images.append({
            "id": "product:" + key, "name": str(item.get("name") or key),
            "image_path": str(path.resolve()), "source": "Vínculo por código",
            "status": "manual", "can_link": True, "product_id": key,
            "kind": "product",
        })

    priority = {"manual": 0, "approved": 1, "pending": 2}
    images.sort(key=lambda item: (priority.get(item["status"], 3),
                                  item["name"].casefold(), item["id"]))
    return {
        "images": images, "counts": counts,
        "legacy_root": str(legacy.resolve()), "products_root": str(products.resolve()),
        "historical_review_note": (
            "Imagens recuperadas do GitHub precisam ser importadas e revisadas "
            "no Banco de Imagens do SR Studio. Pendentes não são vinculadas automaticamente."
        ),
    }
