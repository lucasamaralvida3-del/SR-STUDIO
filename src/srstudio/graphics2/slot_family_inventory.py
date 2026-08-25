from __future__ import annotations

"""Frozen catalog for every reusable ItemSlot family in the Quinta3 corpus."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import os
import sys
from typing import Any


INVENTORY_PATH = Path(__file__).with_name("slot-family-inventory.json")
INVENTORY_SCHEMA = "srstudio/g2-slot-family-inventory/1"


def load_slot_family_inventory() -> dict[str, Any]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    if payload.get("SCHEMA") != INVENTORY_SCHEMA:
        raise ValueError(f"Inventário de slots incompatível: {payload.get('SCHEMA')!r}")
    families = payload.get("FAMILIES")
    if not isinstance(families, list) or len(families) != 17:
        raise ValueError("O corpus Quinta3 precisa expor exatamente 17 famílias reais.")
    ids = [str(item.get("FAMILY_ID") or "") for item in families if isinstance(item, dict)]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError("FAMILY_ID vazio ou duplicado no inventário de slots.")
    if payload.get("PRODUCT_CATEGORY_HARDCODING") is not False:
        raise ValueError("Famílias de ItemSlot não podem depender da categoria do produto.")
    return payload


def slot_family_entries() -> tuple[dict[str, Any], ...]:
    return tuple(deepcopy(item) for item in load_slot_family_inventory()["FAMILIES"])


def slot_family_entry(family_id: str) -> dict[str, Any]:
    key = str(family_id or "").strip()
    for item in load_slot_family_inventory()["FAMILIES"]:
        if str(item.get("FAMILY_ID") or "") == key:
            return deepcopy(item)
    raise KeyError(f"Família real de ItemSlot inexistente: {family_id}")


def slot_family_presets() -> dict[str, dict[str, Any]]:
    presets: dict[str, dict[str, Any]] = {}
    for entry in load_slot_family_inventory()["FAMILIES"]:
        preset = deepcopy(entry["INTERNAL_PRESET"])
        metadata = preset.setdefault("metadata", {})
        metadata.update(
            {
                "catalog_name": str(entry["CATALOG_NAME"]),
                "slot_kind": "multi_item"
                if entry["SINGLE_ITEM_MULTI_ITEM"] == "MULTI_ITEM"
                else "single_item",
                "product_cell_count": int(entry["PRODUCT_CELL_COUNT"]),
                "inventory_schema": INVENTORY_SCHEMA,
                "inventory_family_id": str(entry["FAMILY_ID"]),
                "category_is_not_family": True,
                "product_identity_is_not_family": True,
                "unit_is_not_family": True,
                "image_backplate": False,
            }
        )
        preset["slot_kind"] = metadata["slot_kind"]
        preset["product_cell_count"] = metadata["product_cell_count"]
        preset["catalog_name"] = metadata["catalog_name"]
        presets[str(entry["FAMILY_ID"])] = preset
    return presets


def multi_item_family_ids() -> tuple[str, ...]:
    return tuple(
        str(item["FAMILY_ID"])
        for item in load_slot_family_inventory()["FAMILIES"]
        if item["SINGLE_ITEM_MULTI_ITEM"] == "MULTI_ITEM"
    )


def single_item_family_ids() -> tuple[str, ...]:
    return tuple(
        str(item["FAMILY_ID"])
        for item in load_slot_family_inventory()["FAMILIES"]
        if item["SINGLE_ITEM_MULTI_ITEM"] == "SINGLE_ITEM"
    )


def is_multi_item_family(family_id: str) -> bool:
    return str(family_id or "").strip() in set(multi_item_family_ids())


def slot_font_family(document: Any) -> str:
    """Use exact Anton when available, otherwise its approved Windows fallback."""

    entries = dict(getattr(document, "metadata", {}) or {}).get("embedded_fonts")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict) or str(entry.get("family") or "").casefold() != "anton":
                continue
            if entry.get("runtime_allowed", True) is False:
                continue
            path = Path(str(entry.get("extracted_path") or ""))
            if path.is_file():
                return "Anton"
    cached = _cached_anton_path()
    if cached is not None:
        if not isinstance(entries, list):
            entries = []
            getattr(document, "metadata", {})["embedded_fonts"] = entries
        entries.append(
            {
                "family": "Anton",
                "style": "regular",
                "sha256": sha256(cached.read_bytes()).hexdigest(),
                "extracted_path": str(cached),
                "runtime_allowed": True,
                "source": "srstudio-font-cache",
            }
        )
        return "Anton"
    return "Arial"


def _cached_anton_path() -> Path | None:
    candidates: list[Path] = [*Path(__file__).with_name("fonts").glob("Anton-regular-*.ttf")]
    configured = str(os.environ.get("SRSTUDIO_ANTON_FONT") or "").strip()
    if configured:
        candidates.append(Path(configured))
    roots = [Path.home() / ".srstudio5", Path.cwd() / ".srstudio5"]
    bundle_text = str(getattr(sys, "_MEIPASS", "") or "").strip()
    if bundle_text:
        roots.append(Path(bundle_text))
    executable_root = Path(sys.executable).resolve().parent
    roots.append(executable_root)
    patterns = (
        "imports/*/graphics2/fonts/Anton-regular-*.ttf",
        "graphics2/fonts/Anton-regular-*.ttf",
        "fonts/Anton-regular-*.ttf",
        "Anton-regular-*.ttf",
    )
    seen: set[Path] = set()
    for root in roots:
        for pattern in patterns:
            for path in root.glob(pattern):
                try:
                    resolved = path.resolve()
                except OSError:
                    resolved = path
                if resolved not in seen:
                    seen.add(resolved)
                    candidates.append(resolved)
    return next((path for path in candidates if path.is_file()), None)


def cached_slot_asset_path(file_name: str, expected_sha256: str) -> Path | None:
    """Resolve a frozen corpus decoration from import or packaged asset caches."""

    basename = Path(str(file_name or "")).name
    digest = str(expected_sha256 or "").strip().lower()
    if not basename or len(digest) != 64:
        return None
    roots = [Path.home() / ".srstudio5", Path.cwd() / ".srstudio5", Path(sys.executable).resolve().parent]
    bundle_text = str(getattr(sys, "_MEIPASS", "") or "").strip()
    if bundle_text:
        roots.append(Path(bundle_text))
    candidates: list[Path] = [Path(__file__).with_name("assets") / "slot_families" / basename]
    for root in roots:
        candidates.extend(
            (
                root / "imports-g2" / "artwork" / "media" / basename,
                root / "graphics2" / "assets" / basename,
                root / "assets" / basename,
                root / basename,
            )
        )
        candidates.extend(root.glob(f"imports/*/{basename}"))
    for path in candidates:
        if path.is_file() and sha256(path.read_bytes()).hexdigest().lower() == digest:
            return path.resolve()
    return None


def apply_document_font_fallback(preset: dict[str, Any], document: Any) -> dict[str, Any]:
    resolved = slot_font_family(document)
    preset = deepcopy(preset)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            family = str(value.get("font_family") or "")
            if family.casefold() == "anton":
                value["source_font_family"] = "Anton"
                value["font_family"] = resolved
                if resolved != "Anton":
                    # Source boxes were measured for the narrow Anton face.
                    # Qt's generic fit algorithm can collapse an approved
                    # fallback to its minimum size because Impact has taller
                    # metrics. Keep readable source-scale text and normal wrap.
                    value["fit_inside_box"] = False
                    if str(value.get("semantic_fit_policy") or "").lower() == "overflow_only":
                        value["semantic_fit_policy"] = "fallback_no_shrink"
                    if value.get("font_size") not in (None, ""):
                        value["font_size"] = float(value["font_size"]) * 0.92
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(preset)
    preset.setdefault("metadata", {})["resolved_slot_font_family"] = resolved
    return preset
