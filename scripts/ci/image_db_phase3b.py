from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from srstudio.images.association import normalize_product_name
from srstudio.images.department_coverage import department_coverage, payload as department_payload
from srstudio.images.library import ImageLibrary
from srstudio.images.library_audit import audit_library, payload as audit_payload
from srstudio.images.lookup import ProductImageLookupService
from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_cli import catalog_names_from_sqlite
from srstudio.images.visual_dedup import compact_rgb_signature, is_conservative_visual_duplicate

RELEASE_TAG = "image-db-corpus-v1"
STANDALONE_ASSET = "standalone-images.zip"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
EXPECTED_IMAGE_FILES = 160

IMPORTANT_QUERIES = (
    "LEITE TRIANGULO 1L",
    "ARROZ VASCONCELOS 5KG",
    "FLOCAO SINHA 400G",
    "FEIJAO PARANA 1KG",
    "CARVAO GOBBO",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _request_json(url: str, token: str) -> tuple[int, Any, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "srstudio-image-db-phase3b-ci",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.status), json.load(response), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(body)
        except ValueError:
            payload = {"raw_body": body}
        return int(exc.code), payload, dict(exc.headers.items())


def _append_env(name: str, value: str) -> None:
    env_file = os.environ.get("GITHUB_ENV")
    if not env_file:
        return
    with Path(env_file).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _ascii(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value).lower() if not unicodedata.combining(char)
    )


def _classification(relative_name: str, valid: bool) -> str:
    if not valid:
        return "rejected-corrupt"
    name = _ascii(relative_name)
    screenshot_markers = ("screenshot", "captura de tela", "captura_de_tela", "screen shot", "printscreen")
    if any(marker in name for marker in screenshot_markers):
        return "review-screenshot"
    decorative_markers = (
        "logo", "logomarca", "banner", "fundo", "background", "moldura", "icone", "icon ",
        "qr code", "qrcode", "selo", "placa", "cartaz", "template", "layout", "topo", "story", "post ",
    )
    if any(marker in name for marker in decorative_markers):
        return "rejected-decorative"
    return "candidate"


def _download_release_asset(target_dir: Path, token: str) -> tuple[bool, str]:
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    completed = subprocess.run(
        ["gh", "release", "download", RELEASE_TAG, "-p", STANDALONE_ASSET, "-D", str(target_dir), "--clobber"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        timeout=900,
        check=False,
    )
    return completed.returncode == 0, completed.stdout


def inventory_standalone(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.artifact_dir)
    corpus_dir = Path(args.corpus_dir)
    extract_dir = corpus_dir / "standalone"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    endpoint = f"https://api.github.com/repos/{repository}/releases/tags/{urllib.parse.quote(RELEASE_TAG, safe='')}"
    status, response, headers = _request_json(endpoint, token) if repository and token else (0, {}, {})
    _write_json(
        artifact_dir / "standalone-release-api-response.json",
        {
            "requested_tag": RELEASE_TAG,
            "endpoint": endpoint,
            "http_status": status,
            "response": response,
            "selected_headers": {
                key: value
                for key, value in headers.items()
                if key.lower() in {"content-type", "etag", "last-modified", "x-ratelimit-remaining", "x-ratelimit-reset"}
            },
        },
    )

    release = response if status == 200 and isinstance(response, dict) else {}
    asset = next(
        (item for item in (release.get("assets") or ()) if isinstance(item, dict) and item.get("name") == STANDALONE_ASSET),
        None,
    )
    target = corpus_dir / STANDALONE_ASSET
    download_success = False
    download_output = ""
    if asset:
        try:
            download_success, download_output = _download_release_asset(corpus_dir, token)
        except (OSError, subprocess.SubprocessError) as exc:
            download_output = repr(exc)
    actual_size = target.stat().st_size if target.is_file() else 0
    actual_sha = _sha256(target) if target.is_file() else ""
    expected_size = int((asset or {}).get("size") or 0)
    release_digest = str((asset or {}).get("digest") or "")
    expected_sha = release_digest.split(":", 1)[1].lower() if release_digest.lower().startswith("sha256:") else ""
    size_verified = bool(expected_size and actual_size == expected_size)
    hash_verified = bool(expected_sha and actual_sha == expected_sha)
    zip_integrity = False
    bad_member = None
    zip_error = ""
    if target.is_file():
        try:
            with zipfile.ZipFile(target) as archive:
                bad_member = archive.testzip()
            zip_integrity = bad_member is None
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            zip_error = repr(exc)
    verified = bool(asset and download_success and size_verified and hash_verified and zip_integrity)
    verification = {
        "release_found": bool(release),
        "release_id": release.get("id"),
        "release_name": release.get("name"),
        "asset_found": asset is not None,
        "asset_name": (asset or {}).get("name"),
        "asset_id": (asset or {}).get("id"),
        "expected_size": expected_size,
        "actual_size": actual_size,
        "release_digest": release_digest,
        "sha256": actual_sha,
        "download_complete": bool(target.is_file() and size_verified and zip_integrity),
        "download_command_success": download_success,
        "size_verified": size_verified,
        "hash_verified": hash_verified,
        "zip_integrity": zip_integrity,
        "bad_member": bad_member,
        "zip_error": zip_error,
        "verified": verified,
        "download_output": download_output[-4000:],
    }
    _write_json(artifact_dir / "standalone-asset-verification.json", verification)
    if not verified:
        _append_env("STANDALONE_AVAILABLE", "false")
        _append_env("STANDALONE_CORPUS_VALIDATED", "false")
        return 21

    if extract_dir.exists():
        import shutil
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target) as archive:
        archive.extractall(extract_dir)

    candidates = sorted(
        path for path in extract_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    rows: list[dict[str, Any]] = []
    sha_groups: dict[str, list[int]] = {}
    valid_indices: list[int] = []
    for path in candidates:
        rel = path.relative_to(extract_dir).as_posix()
        sha = _sha256(path)
        width = height = 0
        fmt = ""
        valid = False
        dhash = ""
        rgb_signature = ""
        error = ""
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                prepared = ImageOps.exif_transpose(image)
                width, height = prepared.size
                fmt = str(image.format or path.suffix.lstrip(".")).upper()
                dhash = ImageLibrary._dhash(prepared)
                rgb_signature = compact_rgb_signature(prepared)
            valid = width > 0 and height > 0
        except (OSError, ValueError, RuntimeError) as exc:
            error = repr(exc)
        row = {
            "filename": rel,
            "sha256": sha,
            "size": path.stat().st_size,
            "width": width,
            "height": height,
            "format": fmt,
            "provenance": {
                "source_kind": "github-release-standalone",
                "release_tag": RELEASE_TAG,
                "release_id": release.get("id"),
                "asset_id": (asset or {}).get("id"),
                "asset_name": STANDALONE_ASSET,
                "zip_member": rel,
            },
            "classification": _classification(rel, valid),
            "valid": valid,
            "error": error,
            "dhash": dhash,
            "rgb_signature": rgb_signature,
            "exact_duplicate": False,
            "exact_duplicate_group": None,
            "near_duplicate_group": None,
        }
        rows.append(row)
        sha_groups.setdefault(sha, []).append(len(rows) - 1)
        if valid:
            valid_indices.append(len(rows) - 1)

    exact_groups = [indices for indices in sha_groups.values() if len(indices) > 1]
    for group_no, indices in enumerate(exact_groups, start=1):
        for index in indices:
            rows[index]["exact_duplicate"] = True
            rows[index]["exact_duplicate_group"] = group_no

    parent = list(range(len(rows)))
    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    near_pairs = 0
    for offset, left_index in enumerate(valid_indices):
        left = rows[left_index]
        for right_index in valid_indices[offset + 1 :]:
            right = rows[right_index]
            if left["sha256"] == right["sha256"]:
                continue
            if is_conservative_visual_duplicate(
                left["dhash"],
                right["dhash"],
                (left["width"], left["height"]),
                (right["width"], right["height"]),
                left_rgb_signature=left["rgb_signature"],
                right_rgb_signature=right["rgb_signature"],
            ):
                near_pairs += 1
                union(left_index, right_index)

    near_components: dict[int, list[int]] = {}
    for index in valid_indices:
        root = find(index)
        near_components.setdefault(root, []).append(index)
    near_groups = [indices for indices in near_components.values() if len(indices) > 1]
    for group_no, indices in enumerate(near_groups, start=1):
        for index in indices:
            rows[index]["near_duplicate_group"] = group_no

    valid_count = sum(1 for row in rows if row["valid"])
    corrupt_count = len(rows) - valid_count
    decorative_count = sum(1 for row in rows if row["classification"].startswith("rejected-"))
    screenshot_count = sum(1 for row in rows if row["classification"] == "review-screenshot")
    candidate_count = sum(1 for row in rows if row["classification"] == "candidate")
    exact_duplicate_observations = sum(len(indices) - 1 for indices in exact_groups)
    manifest = {
        "version": 1,
        "release_tag": RELEASE_TAG,
        "asset": {
            "id": (asset or {}).get("id"),
            "name": STANDALONE_ASSET,
            "size": actual_size,
            "sha256": actual_sha,
            "verified": verified,
        },
        "metrics": {
            "image_files": len(rows),
            "expected_image_files": EXPECTED_IMAGE_FILES,
            "valid_images": valid_count,
            "corrupt_images": corrupt_count,
            "candidate_images": candidate_count,
            "decorative_rejected": decorative_count,
            "screenshots_review": screenshot_count,
            "exact_duplicate_groups": len(exact_groups),
            "exact_duplicate_observations": exact_duplicate_observations,
            "near_duplicate_groups": len(near_groups),
            "near_duplicate_pairs": near_pairs,
        },
        "images": rows,
    }
    _write_json(artifact_dir / "standalone-manifest.json", manifest)

    training_rows = []
    for row in rows:
        if not row["valid"] or row["classification"] != "candidate":
            continue
        training_rows.append(
            {
                "path": row["filename"],
                "verified": False,
                "provenance": row["provenance"],
            }
        )
    training_manifest = extract_dir / "training-manifest.json"
    _write_json(training_manifest, {"images": training_rows})
    _write_json(
        artifact_dir / "standalone-training-selection.json",
        {
            "selected": len(training_rows),
            "excluded": len(rows) - len(training_rows),
            "manifest": str(training_manifest),
        },
    )

    corpus_validated = bool(len(rows) == EXPECTED_IMAGE_FILES and verified)
    _append_env("STANDALONE_AVAILABLE", "true" if corpus_validated else "false")
    _append_env("STANDALONE_CORPUS_VALIDATED", "true" if corpus_validated else "false")
    _append_env("STANDALONE_DIR", str(extract_dir))
    _append_env("STANDALONE_MANIFEST", str(training_manifest))
    _append_env("STANDALONE_TOTAL_FILES", str(len(rows)))
    _append_env("STANDALONE_TRAINING_FILES", str(len(training_rows)))
    return 0 if corpus_validated else 22


def _canonical_sha(asset: Any) -> str:
    metadata = dict(getattr(asset, "metadata", {}) or {})
    sha = str(metadata.get("sha256_full") or metadata.get("sha256") or "").lower()
    if len(sha) == 64:
        return sha
    path = Path(str(getattr(asset, "path", "")))
    return _sha256(path) if path.is_file() else ""


def library_snapshot(library_root: Path) -> dict[str, Any]:
    library = SafeImageLibrary(library_root)
    assets = list(library.all())
    logical_rows: list[dict[str, Any]] = []
    for asset in assets:
        metadata = dict(asset.metadata or {})
        provenance = []
        for item in metadata.get("provenance") or ():
            if isinstance(item, dict):
                provenance.append(
                    {
                        "source_kind": item.get("source_kind"),
                        "source_file": item.get("source_file") or item.get("zip_member"),
                        "asset_id": item.get("asset_id"),
                        "release_tag": item.get("release_tag"),
                    }
                )
        logical_rows.append(
            {
                "sha256": _canonical_sha(asset),
                "product": normalize_product_name(asset.product_name or asset.product_key),
                "review_status": asset.review_status,
                "confidence": round(float(asset.confidence or 0.0), 6),
                "perceptual_hash": str(asset.perceptual_hash or ""),
                "aliases": sorted(normalize_product_name(value) for value in (asset.aliases or ()) if value),
                "variant_sha256": sorted(str(value) for value in (metadata.get("variant_sha256") or ())),
                "association_status": metadata.get("association_status"),
                "standalone": bool(metadata.get("standalone")),
                "provenance": sorted(provenance, key=lambda row: json.dumps(row, sort_keys=True, default=str)),
            }
        )
    logical_rows.sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))
    digest = hashlib.sha256(json.dumps(logical_rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "canonical": len(assets),
        "physical": sum(Path(str(asset.path)).is_file() for asset in assets),
        "accepted": sum(asset.review_status == "accepted" for asset in assets),
        "pending": sum(asset.review_status == "pending" for asset in assets),
        "rejected": sum(asset.review_status == "rejected" for asset in assets),
        "missing_provenance": sum(
            1
            for asset in assets
            if not (asset.metadata or {}).get("provenance") and not asset.source_file and not asset.source
        ),
        "logical_signature_sha256": digest,
        "logical_rows": logical_rows,
    }


def snapshot_command(args: argparse.Namespace) -> int:
    payload = library_snapshot(Path(args.library))
    _write_json(Path(args.output), payload)
    return 0


def _coverage_for_library(library_root: Path, product_db: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = catalog_names_from_sqlite(product_db)
    audit = audit_library(SafeImageLibrary(library_root), catalog, IMPORTANT_QUERIES, top_missing_limit=100)
    audit_data = audit_payload(audit)
    metrics = audit_data["metrics"]
    total = int(metrics.get("catalog_products", 0))
    auto = int(metrics.get("catalog_auto_approved", 0))
    likely = int(metrics.get("catalog_likely", 0))
    review = int(metrics.get("catalog_review_required", 0))
    missing = int(metrics.get("catalog_without_any_image", 0))
    any_candidate = auto + likely + review
    coverage = {
        "total": total,
        "auto_approved": auto,
        "likely": likely,
        "review_required": review,
        "missing": missing,
        "any_candidate": any_candidate,
        "any_candidate_coverage_percent": round(100.0 * any_candidate / max(1, total), 4),
        "auto_approved_coverage_percent": round(100.0 * auto / max(1, total), 4),
    }
    departments = department_payload(department_coverage(SafeImageLibrary(library_root), catalog))
    return coverage, departments


def compare_libraries(args: argparse.Namespace) -> int:
    left = library_snapshot(Path(args.left_library))
    right = library_snapshot(Path(args.right_library))
    left_cov, left_dep = _coverage_for_library(Path(args.left_library), Path(args.product_db))
    right_cov, right_dep = _coverage_for_library(Path(args.right_library), Path(args.product_db))
    result = {
        "left": {key: value for key, value in left.items() if key != "logical_rows"},
        "right": {key: value for key, value in right.items() if key != "logical_rows"},
        "logical_signature_equal": left["logical_signature_sha256"] == right["logical_signature_sha256"],
        "canonical_equal": left["canonical"] == right["canonical"],
        "physical_equal": left["physical"] == right["physical"],
        "coverage_equal": left_cov == right_cov,
        "departments_equal": left_dep == right_dep,
        "left_coverage": left_cov,
        "right_coverage": right_cov,
    }
    result["pass"] = all(
        result[key]
        for key in ("logical_signature_equal", "canonical_equal", "physical_equal", "coverage_equal", "departments_equal")
    )
    _write_json(Path(args.output), result)
    return 0 if result["pass"] else 31


def top_delta(args: argparse.Namespace) -> int:
    def rows(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    before = rows(Path(args.before))
    after = rows(Path(args.after))
    def key(row: dict[str, str]) -> str:
        return normalize_product_name(row.get("normalized_name") or row.get("display_name") or row.get("product_name") or "")
    after_keys = {key(row) for row in after}
    exited = [row for row in before if key(row) and key(row) not in after_keys]
    payload = {
        "before_top100_count": len(before),
        "after_top100_count": len(after),
        "exited_missing_count": len(exited),
        "exited": exited,
    }
    _write_json(Path(args.output), payload)
    return 0


def _lookup_row(service: ProductImageLookupService, query: str) -> dict[str, Any]:
    result = service.find_image(query)
    best = result.best_match
    asset = best.asset if best else None
    return {
        "query": query,
        "found": best is not None,
        "product_name": str(getattr(asset, "product_name", "") or "") if asset else "",
        "image_id": str(getattr(asset, "id", "") or "") if asset else "",
        "review_status": str(getattr(asset, "review_status", "") or "") if asset else "",
        "asset_confidence": float(getattr(asset, "confidence", 0.0) or 0.0) if asset else 0.0,
        "confidence": result.confidence,
        "match_type": result.match_type,
        "quality_score": result.quality_score,
        "provenance": list(result.provenance),
    }


def important_queries(args: argparse.Namespace) -> int:
    service = ProductImageLookupService(SafeImageLibrary(args.library))
    service.refresh()
    queries = list(IMPORTANT_QUERIES)
    if args.standalone_report and Path(args.standalone_report).is_file():
        report = json.loads(Path(args.standalone_report).read_text(encoding="utf-8"))
        for match in report.get("matches") or ():
            product = str(match.get("product_name") or "")
            if product and product not in queries:
                queries.append(product)
            if len(queries) >= 15:
                break
    _write_json(Path(args.output), {"queries": [_lookup_row(service, query) for query in queries]})
    return 0


def new_auto_review(args: argparse.Namespace) -> int:
    before_payload = json.loads(Path(args.before_index).read_text(encoding="utf-8"))
    before_accepted: set[tuple[str, str]] = set()
    for data in before_payload.values():
        if not isinstance(data, dict) or data.get("review_status") != "accepted":
            continue
        metadata = dict(data.get("metadata") or {})
        sha = str(metadata.get("sha256_full") or metadata.get("sha256") or "")
        product = normalize_product_name(data.get("product_name") or data.get("product_key") or "")
        before_accepted.add((sha, product))

    library = SafeImageLibrary(args.library)
    rows: list[dict[str, Any]] = []
    for asset in library.all():
        if asset.review_status != "accepted":
            continue
        sha = _canonical_sha(asset)
        product = normalize_product_name(asset.product_name or asset.product_key)
        if (sha, product) in before_accepted:
            continue
        metadata = dict(asset.metadata or {})
        provenance = list(metadata.get("provenance") or ())
        if not metadata.get("standalone") and not any(
            isinstance(item, dict) and item.get("source_kind") in {"standalone-library", "github-release-standalone"}
            for item in provenance
        ):
            continue
        rows.append(
            {
                "image_id": asset.id,
                "product_name": asset.product_name,
                "product_key": asset.product_key,
                "path": asset.path,
                "sha256": sha,
                "confidence": asset.confidence,
                "review_status": asset.review_status,
                "provenance": provenance,
            }
        )
    rows.sort(key=lambda row: (str(row["product_name"]), str(row["sha256"])))
    _write_json(Path(args.output_manifest), {"sample_size": len(rows), "images": rows})

    target = Path(args.output_sheet)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        image = Image.new("RGB", (1000, 180), "white")
        draw = ImageDraw.Draw(image)
        draw.text((30, 70), "Phase 3B: no new auto-approved standalone associations", fill="black")
        image.save(target)
        return 0

    columns = 4
    cell_w, cell_h = 320, 360
    rows_n = (len(rows) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows_n * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(rows):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        path = Path(str(row["path"]))
        try:
            with Image.open(path) as source:
                thumb = ImageOps.exif_transpose(source).convert("RGB")
                thumb.thumbnail((280, 260))
                sheet.paste(thumb, (x + 20, y + 10))
        except OSError:
            pass
        draw.text((x + 10, y + 280), f"#{index+1} {row['product_name']}", fill="black")
        draw.text((x + 10, y + 305), f"conf={row['confidence']:.4f}", fill="black")
        draw.text((x + 10, y + 330), str(row["sha256"])[:20], fill="black")
    sheet.save(target)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3B operational validation helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory")
    inv.add_argument("--artifact-dir", required=True)
    inv.add_argument("--corpus-dir", required=True)
    inv.set_defaults(func=inventory_standalone)

    snap = sub.add_parser("snapshot")
    snap.add_argument("--library", required=True)
    snap.add_argument("--output", required=True)
    snap.set_defaults(func=snapshot_command)

    compare = sub.add_parser("compare")
    compare.add_argument("--left-library", required=True)
    compare.add_argument("--right-library", required=True)
    compare.add_argument("--product-db", required=True)
    compare.add_argument("--output", required=True)
    compare.set_defaults(func=compare_libraries)

    delta = sub.add_parser("top-delta")
    delta.add_argument("--before", required=True)
    delta.add_argument("--after", required=True)
    delta.add_argument("--output", required=True)
    delta.set_defaults(func=top_delta)

    important = sub.add_parser("important")
    important.add_argument("--library", required=True)
    important.add_argument("--standalone-report")
    important.add_argument("--output", required=True)
    important.set_defaults(func=important_queries)

    auto = sub.add_parser("new-auto")
    auto.add_argument("--before-index", required=True)
    auto.add_argument("--library", required=True)
    auto.add_argument("--output-manifest", required=True)
    auto.add_argument("--output-sheet", required=True)
    auto.set_defaults(func=new_auto_review)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
