# Phase 3A explicit Release-corpus validation.
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

RELEASE_TAG = "image-db-corpus-v1"
PRIMARY_ASSETS = (
    "Downloads(1)(1).zip",
    "Downloads(2)(1).zip",
    "publish_repository.zip",
)
DEFERRED_ASSET = "standalone-images.zip"
DISCOVER_ASSETS = PRIMARY_ASSETS + (DEFERRED_ASSET,)


def _request_json(url: str, token: str) -> tuple[int, Any, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "srstudio-image-db-phase3-ci",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.status), json.load(response), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(body)
        except ValueError:
            parsed = {"raw_body": body}
        return int(exc.code), parsed, dict(exc.headers.items())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_env(name: str, value: str) -> None:
    env_path = os.environ.get("GITHUB_ENV")
    if not env_path:
        return
    with Path(env_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _download_with_gh(name: str, target_dir: Path, token: str) -> tuple[bool, str]:
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    completed = subprocess.run(
        ["gh", "release", "download", RELEASE_TAG, "-p", name, "-D", str(target_dir), "--clobber"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        timeout=900,
        check=False,
    )
    return completed.returncode == 0, completed.stdout


def _verify_zip(name: str, meta: dict[str, Any] | None, corpus_dir: Path, token: str) -> dict[str, Any]:
    target = corpus_dir / name
    row: dict[str, Any] = {
        "name": name,
        "release_found": meta is not None,
        "asset_id": (meta or {}).get("asset_id"),
        "path": str(target),
        "expected_size": int((meta or {}).get("size") or 0),
        "release_digest": str((meta or {}).get("digest") or ""),
        "tag": RELEASE_TAG,
        "download_complete": False,
    }
    if meta:
        try:
            ok, output = _download_with_gh(name, corpus_dir, token)
            row["download_command_success"] = ok
            row["download_output"] = output[-4000:]
        except (OSError, subprocess.SubprocessError) as exc:
            row["download_command_success"] = False
            row["download_error"] = repr(exc)

    row["exists"] = target.is_file()
    row["actual_size"] = target.stat().st_size if target.is_file() else 0
    row["sha256"] = _sha256(target) if target.is_file() else ""
    expected_digest = row["release_digest"].lower()
    expected_hash = expected_digest.split(":", 1)[1] if expected_digest.startswith("sha256:") else ""
    row["size_verified"] = bool(row["expected_size"] > 0 and row["actual_size"] == row["expected_size"])
    row["hash_verified"] = bool(row["sha256"] and (not expected_hash or row["sha256"] == expected_hash))
    row["hash_verification_basis"] = "release-digest" if expected_hash else "downloaded-sha256-recorded"
    if target.is_file():
        try:
            with zipfile.ZipFile(target) as archive:
                bad_member = archive.testzip()
            row["zip_integrity"] = bad_member is None
            row["bad_member"] = bad_member
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            row["zip_integrity"] = False
            row["zip_error"] = repr(exc)
    else:
        row["zip_integrity"] = False
    row["download_complete"] = bool(row["exists"] and row["size_verified"] and row["zip_integrity"])
    row["verified"] = bool(row["release_found"] and row["download_complete"] and row["hash_verified"])
    return row


def _catalog_metrics(db_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "db_path": str(db_path),
        "exists": db_path.is_file(),
        "products": None,
        "historical_records": None,
        "products_expected": 520,
        "historical_records_expected": 3116,
        "pass": False,
    }
    if not db_path.is_file():
        return result
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        result["products"] = int(connection.execute("SELECT COUNT(*) FROM produtos").fetchone()[0])
        result["historical_records"] = int(connection.execute("SELECT COUNT(*) FROM itens_relatorio").fetchone()[0])
    finally:
        connection.close()
    result["pass"] = bool(result["products"] == 520 and result["historical_records"] == 3116)
    return result


def main() -> int:
    artifact_dir = Path(os.environ.get("ARTIFACT_DIR", "artifacts/image-db-phase3"))
    corpus_dir = Path(os.environ.get("CORPUS_DIR", ".phase3-corpus"))
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if corpus_dir.exists():
        shutil.rmtree(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    release: dict[str, Any] = {}
    api_status = 0
    api_payload: Any = {}
    api_headers: dict[str, str] = {}
    endpoint = ""

    if not repository or not token:
        errors.append("GITHUB_REPOSITORY/GITHUB_TOKEN unavailable")
    else:
        endpoint = f"https://api.github.com/repos/{repository}/releases/tags/{urllib.parse.quote(RELEASE_TAG, safe='')}"
        try:
            api_status, api_payload, api_headers = _request_json(endpoint, token)
            if api_status == 200 and isinstance(api_payload, dict):
                release = api_payload
            else:
                errors.append(f"explicit release lookup failed: HTTP {api_status}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"explicit release lookup failed: {exc!r}")

    _write_json(
        artifact_dir / "release-api-response.json",
        {
            "requested_tag": RELEASE_TAG,
            "endpoint": endpoint,
            "http_status": api_status,
            "response": api_payload,
            "selected_headers": {
                key: value
                for key, value in api_headers.items()
                if key.lower() in {"content-type", "etag", "last-modified", "x-ratelimit-remaining", "x-ratelimit-reset"}
            },
        },
    )

    returned_tag = str(release.get("tag_name") or "")
    all_release_assets: list[dict[str, Any]] = []
    found: dict[str, dict[str, Any]] = {}
    if release and returned_tag != RELEASE_TAG:
        errors.append(f"explicit release tag mismatch: expected={RELEASE_TAG!r} got={returned_tag!r}")
    for asset in release.get("assets") or ():
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        item = {
            "name": name,
            "asset_id": asset.get("id"),
            "size": int(asset.get("size") or 0),
            "digest": str(asset.get("digest") or ""),
            "state": asset.get("state"),
            "created_at": asset.get("created_at"),
            "updated_at": asset.get("updated_at"),
            "browser_download_url": asset.get("browser_download_url"),
        }
        all_release_assets.append(item)
        if name not in DISCOVER_ASSETS:
            continue
        found[name] = {
            **item,
            "tag": returned_tag,
            "release_id": release.get("id"),
            "release_name": release.get("name"),
            "release_draft": bool(release.get("draft")),
            "release_prerelease": bool(release.get("prerelease")),
        }

    release_payload = {
        "lookup_mode": "explicit-tag-only",
        "requested_tag": RELEASE_TAG,
        "api_http_status": api_status,
        "release_found": bool(release),
        "release_tag": returned_tag,
        "release_id": release.get("id"),
        "release_name": release.get("name"),
        "release_draft": bool(release.get("draft")) if release else False,
        "release_prerelease": bool(release.get("prerelease")) if release else False,
        "all_assets_returned": all_release_assets,
        "phase3a_required": list(PRIMARY_ASSETS),
        "standalone_phase": "DEFERRED",
        "standalone_asset": DEFERRED_ASSET,
        "found": found,
        "missing_phase3a_required": [name for name in PRIMARY_ASSETS if name not in found],
        "errors": errors,
        "release_count_scanned": 1 if release else 0,
    }
    _write_json(artifact_dir / "release-assets.json", release_payload)

    verification: dict[str, dict[str, Any]] = {}
    download_log: list[str] = []
    for name in PRIMARY_ASSETS:
        row = _verify_zip(name, found.get(name), corpus_dir, token)
        verification[name] = row
        download_log.append(
            f"[{name}] asset_id={row.get('asset_id')} found={row['release_found']} "
            f"download_complete={row['download_complete']} size={row['actual_size']} sha256={row['sha256']} "
            f"verified={row['verified']}\n{row.get('download_output', row.get('download_error', ''))}"
        )

    standalone_meta = found.get(DEFERRED_ASSET)
    verification[DEFERRED_ASSET] = {
        "name": DEFERRED_ASSET,
        "phase": "DEFERRED",
        "release_found": standalone_meta is not None,
        "asset_id": (standalone_meta or {}).get("asset_id"),
        "expected_size": int((standalone_meta or {}).get("size") or 0),
        "release_digest": str((standalone_meta or {}).get("digest") or ""),
        "download_complete": False,
        "verified": False,
        "processed": False,
    }

    (artifact_dir / "corpus-download.log").write_text("\n\n".join(download_log), encoding="utf-8")
    primary_verified = all(verification[name]["verified"] for name in PRIMARY_ASSETS)
    _write_json(
        artifact_dir / "corpus-download-verification.json",
        {
            "requested_tag": RELEASE_TAG,
            "phase": "3A",
            "standalone_phase": "DEFERRED",
            "all_phase3a_required_verified": primary_verified,
            "assets": verification,
            "errors": errors,
        },
    )

    zip1 = corpus_dir / "Downloads(1)(1).zip"
    zip2 = corpus_dir / "Downloads(2)(1).zip"
    publish = corpus_dir / "publish_repository.zip"
    (artifact_dir / "corpus-paths.txt").write_text(
        f"zip1={zip1}\nzip2={zip2}\npublish_repository={publish}\nstandalone=DEFERRED\n",
        encoding="utf-8",
    )

    rich_available = bool(
        verification["Downloads(1)(1).zip"]["verified"]
        and verification["Downloads(2)(1).zip"]["verified"]
    )
    product_db = ""
    catalog_metrics: dict[str, Any] = {
        "db_path": "",
        "exists": False,
        "products": None,
        "historical_records": None,
        "products_expected": 520,
        "historical_records_expected": 3116,
        "pass": False,
    }
    if verification["publish_repository.zip"]["verified"]:
        try:
            publish_dir = corpus_dir / "publish"
            publish_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(publish) as archive:
                archive.extractall(publish_dir)
            db = next(publish_dir.rglob("atacado_historico.db"), None)
            if db:
                product_db = str(db)
                catalog_metrics = _catalog_metrics(db)
            else:
                errors.append("publish_repository.zip did not contain atacado_historico.db")
        except (OSError, zipfile.BadZipFile, RuntimeError, sqlite3.Error) as exc:
            errors.append(f"catalog extract/validation failed: {exc!r}")

    _write_json(artifact_dir / "catalog-source-validation.json", catalog_metrics)
    catalog_available = bool(product_db and catalog_metrics.get("pass"))
    standalone_available = False

    _append_env("CORPUS_INTEGRITY_PASS", "true" if primary_verified else "false")
    _append_env("RICH_CORPUS_AVAILABLE", "true" if rich_available else "false")
    _append_env("CATALOG_AVAILABLE", "true" if catalog_available else "false")
    _append_env("STANDALONE_AVAILABLE", "false")
    _append_env("STANDALONE_PHASE", "DEFERRED")
    _append_env("STANDALONE_VALIDATION", "DEFERRED")
    if product_db:
        _append_env("PRODUCT_DB", product_db)

    availability = {
        "requested_release_tag": RELEASE_TAG,
        "phase": "3A",
        "standalone_phase": "DEFERRED",
        "standalone_validation": "DEFERRED",
        "corpus_integrity_pass": primary_verified,
        "rich_corpus_available": rich_available,
        "catalog_available": catalog_available,
        "standalone_available": standalone_available,
        "product_db": product_db,
        "catalog_metrics": catalog_metrics,
        "release_assets": release_payload,
        "verification": verification,
        "expected": {
            "pptx": 36,
            "slides": 566,
            "embedded_unique": 1910,
            "media_occurrences": 2324,
            "standalone": "DEFERRED",
            "catalog_products": 520,
            "catalog_historical_records": 3116,
        },
        "errors": errors,
    }
    _write_json(artifact_dir / "corpus-availability.json", availability)
    print(json.dumps(availability, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
