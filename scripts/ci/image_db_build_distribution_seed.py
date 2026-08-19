from __future__ import annotations

"""Build a distributable bootstrap of the existing SR Image Database.

No product-image association or matching is trained here. The script receives
an already approved logical index and materializes exactly those canonical
assets from approved corpus archives by SHA-256. Output is only transport for
the same ~/.srstudio5/images database used by SR Studio.
"""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable
import io
import json
import zipfile

SEED_SCHEMA = "SRSTUDIO_IMAGE_DB_SEED_1"


def require(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ValueError(f"required field missing: {key}")
    return mapping[key]


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest().lower()


def canonical_sha(raw: dict[str, Any]) -> str:
    metadata = require(raw, "metadata")
    if not isinstance(metadata, dict):
        raise ValueError("asset metadata must be an object")
    value = str(require(metadata, "sha256_full")).strip().lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"invalid sha256_full: {value!r}")
    return value


def provenance_present(raw: dict[str, Any]) -> bool:
    metadata = require(raw, "metadata")
    return bool(metadata.get("source_provenance") or metadata.get("provenance"))


def iter_embedded_pptx_media(outer_path: Path) -> Iterable[tuple[str, bytes]]:
    with zipfile.ZipFile(outer_path) as outer:
        for outer_name in outer.namelist():
            if not outer_name.lower().endswith(".pptx"):
                continue
            try:
                pptx_bytes = outer.read(outer_name)
                with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as pptx:
                    for member in pptx.namelist():
                        normalized = member.replace("\\", "/").lower()
                        if member.endswith("/") or "/media/" not in normalized:
                            continue
                        yield f"{outer_path.name}:{outer_name}:{member}", pptx.read(member)
            except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ValueError(f"corrupt PPTX corpus member {outer_path.name}:{outer_name}: {exc}") from exc


def iter_direct_images(archive_path: Path) -> Iterable[tuple[str, bytes]]:
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            if member.endswith("/") or Path(member).suffix.lower() not in allowed:
                continue
            yield f"{archive_path.name}:{member}", archive.read(member)


def build(args) -> int:
    index_source = Path(args.index).resolve()
    output = Path(args.output).resolve()
    catalog_report = Path(args.catalog_report).resolve()
    audit_report = Path(args.audit_report).resolve()

    payload = json.loads(index_source.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_report.read_text(encoding="utf-8"))
    audit_doc = json.loads(audit_report.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("approved Image DB index must be a non-empty object")
    if not isinstance(catalog, dict):
        raise ValueError("coverage catalog report must be an object")
    if not isinstance(audit_doc, dict):
        raise ValueError("library audit report must be an object")
    audit = require(audit_doc, "metrics")
    if not isinstance(audit, dict):
        raise ValueError("library audit metrics must be an object")

    total_products = require(catalog, "total")
    physical_images = require(audit, "physical_images")
    canonical_assets = require(audit, "canonical_assets")
    provenance_missing = require(audit, "associations_without_provenance")
    if type(total_products) is not int or total_products <= 0:
        raise ValueError("catalog total must be a positive integer")
    if canonical_assets != len(payload) or physical_images != len(payload):
        raise ValueError(
            f"approved index/audit mismatch: index={len(payload)} canonical={canonical_assets} physical={physical_images}"
        )
    if provenance_missing != 0:
        raise ValueError(f"approved audit reports missing provenance: {provenance_missing}")

    wanted: dict[str, list[str]] = {}
    relocated: dict[str, dict[str, Any]] = {}
    for asset_id, raw_value in payload.items():
        if not isinstance(raw_value, dict):
            raise ValueError(f"invalid asset record: {asset_id}")
        raw = dict(raw_value)
        if str(require(raw, "id")) != str(asset_id):
            raise ValueError(f"image_id mismatch: {asset_id}")
        if not provenance_present(raw):
            raise ValueError(f"provenance missing: {asset_id}")
        canonical = canonical_sha(raw)
        suffix = Path(str(require(raw, "path"))).suffix.lower() or ".png"
        filename = f"{asset_id}{suffix}"
        raw["path"] = f"assets/{filename}"
        relocated[str(asset_id)] = raw
        wanted.setdefault(canonical, []).append(filename)

    materialized: dict[str, bytes] = {}

    def consider(data: bytes) -> None:
        digest = digest_bytes(data)
        filenames = wanted.get(digest)
        if not filenames:
            return
        for filename in filenames:
            if filename in materialized and materialized[filename] != data:
                raise ValueError(f"same canonical image restored with divergent bytes: {filename}")
            materialized[filename] = data

    for raw in args.pptx_archive:
        path = Path(raw).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        for _, data in iter_embedded_pptx_media(path):
            consider(data)

    for raw in args.image_archive:
        path = Path(raw).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        for _, data in iter_direct_images(path):
            consider(data)

    missing = sorted(
        Path(str(raw["path"])).name
        for raw in relocated.values()
        if Path(str(raw["path"])).name not in materialized
    )
    if missing:
        raise ValueError(f"{len(missing)} approved image(s) could not be materialized: {missing[:10]}")

    canonical_index = json.dumps(
        relocated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    index_sha = sha256(canonical_index).hexdigest().lower()

    accepted = sum(1 for raw in relocated.values() if str(require(raw, "review_status")) == "accepted")
    pending = sum(1 for raw in relocated.values() if str(require(raw, "review_status")) == "pending")
    rejected = sum(1 for raw in relocated.values() if str(require(raw, "review_status")) == "rejected")

    manifest = {
        "schema": SEED_SCHEMA,
        "catalog_version": args.catalog_version,
        "total_products": total_products,
        "total_images": len(relocated),
        "accepted_images": accepted,
        "pending_images": pending,
        "rejected_images": rejected,
        "index_sha256": index_sha,
        "source_release": args.source_release,
        "source_artifact": args.source_artifact,
        "source_index_sha256": sha256(index_source.read_bytes()).hexdigest().lower(),
        "source_catalog_sha256": sha256(catalog_report.read_bytes()).hexdigest().lower(),
        "source_audit_sha256": sha256(audit_report.read_bytes()).hexdigest().lower(),
        "provenance_status": "PASS",
        "dedup_status": "PASS",
        "lookup_system": "SafeImageLibrary + ProductImageLookupService",
        "persistent_root": "~/.srstudio5/images",
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("index.json", json.dumps(relocated, ensure_ascii=False, indent=2).encode("utf-8"))
        archive.writestr("seed-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        for filename in sorted(materialized):
            archive.writestr(f"assets/{filename}", materialized[filename])

    with zipfile.ZipFile(output) as archive:
        asset_names = [name for name in archive.namelist() if name.startswith("assets/") and not name.endswith("/")]
        if len(asset_names) != len(relocated):
            raise ValueError("seed asset count changed after ZIP creation")
        reopened_manifest = json.loads(archive.read("seed-manifest.json"))
        for key in (
            "schema", "catalog_version", "total_products", "total_images", "index_sha256",
            "source_release", "source_artifact", "provenance_status", "dedup_status",
        ):
            require(reopened_manifest, key)

    print(json.dumps({
        "seed": str(output),
        "seed_sha256": sha256(output.read_bytes()).hexdigest().lower(),
        "seed_bytes": output.stat().st_size,
        **manifest,
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--catalog-report", required=True)
    parser.add_argument("--audit-report", required=True)
    parser.add_argument("--pptx-archive", action="append", default=[])
    parser.add_argument("--image-archive", action="append", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--catalog-version", default="image-db-corpus-v1/coverage-520")
    parser.add_argument("--source-release", default="image-db-corpus-v1")
    parser.add_argument("--source-artifact", required=True)
    return build(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
