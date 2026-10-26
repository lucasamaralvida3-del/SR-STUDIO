"""Read-only campaign artwork bundled by the automatic Beta updater.

No import step or user-supplied paths: PyInstaller --collect-data srstudio
includes the catalog, 12 complete WebP artworks and 12 matching thumbnails.
Only checksum-verified files from the same bundled directory are exposed.
"""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

CATALOG_FORMAT = "SRSTUDIO_BUILTIN_CAMPAIGN_ART_1"


def builtin_campaign_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "campaigns"


@lru_cache(maxsize=1)
def builtin_campaign_catalog() -> dict:
    root = builtin_campaign_root().resolve()
    index = root / "catalog.json"
    if not index.is_file():
        return {"assets": [], "default_seals": {}}
    try:
        manifest = json.loads(index.read_text(encoding="utf-8"))
        if (not isinstance(manifest, dict)
                or manifest.get("format") != CATALOG_FORMAT):
            return {"assets": [], "default_seals": {}}
        rows: list[dict] = []
        for record in manifest.get("assets", []):
            if not isinstance(record, dict) or record.get("kind") not in ("background", "seal"):
                continue
            image = root / str(record.get("path") or "")
            preview = root / str(record.get("thumbnail") or "")
            if (not image.resolve().is_relative_to(root)
                    or not preview.resolve().is_relative_to(root)
                    or not image.is_file() or not preview.is_file()):
                continue
            try:
                if image.stat().st_size != record["size"] or preview.stat().st_size != record["thumbnail_size"]:
                    continue
                if sha256(image.read_bytes()).hexdigest() != record["sha256"]:
                    continue
                if sha256(preview.read_bytes()).hexdigest() != record["thumbnail_sha256"]:
                    continue
            except (OSError, TypeError, KeyError):
                continue
            rows.append({
                "id": str(record.get("id") or ""),
                "campaign_id": str(record.get("campaign_id") or ""),
                "kind": record["kind"],
                "name": str(record.get("name") or image.stem),
                "path": str(image.resolve()),
                "preview_url": preview.resolve().as_uri(),
                "source": "builtin",
            })
        return {
            "assets": rows,
            "default_seals": manifest.get("default_seals") or {},
        }
    except (OSError, ValueError, TypeError):
        return {"assets": [], "default_seals": {}}


def builtin_campaign_assets() -> list[dict]:
    return list(builtin_campaign_catalog()["assets"])


def find_builtin_campaign_asset(asset_id: str, *, expected_kind: str | None = None) -> dict:
    asset = next((a for a in builtin_campaign_assets()
                  if a["id"] == asset_id), None)
    if asset is None or (expected_kind is not None and asset["kind"] != expected_kind):
        raise ValueError("Arte da campanha não está disponível na instalação.")
    return asset


def default_seal_for_campaign(campaign_id: str) -> dict:
    seal_id = str(builtin_campaign_catalog()["default_seals"].get(campaign_id) or "")
    result = find_builtin_campaign_asset(seal_id, expected_kind="seal")
    if result["campaign_id"] != campaign_id:
        raise ValueError("Selo padrão não corresponde à campanha.")
    return result
