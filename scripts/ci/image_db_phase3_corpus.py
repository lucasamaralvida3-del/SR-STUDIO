# Phase 3 explicit Release-corpus validation.
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

RELEASE_TAG = "image-db-corpus-v1"
REQUIRED_ASSETS = (
    "Downloads(1)(1).zip",
    "Downloads(2)(1).zip",
    "publish_repository.zip",
    "standalone-images.zip",
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


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
        endpoint = (
            f"https://api.github.com/repos/{repository}/releases/tags/"
            f"{urllib.parse.quote(RELEASE_TAG, safe='')}"
        )
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
    found: dict[str, dict[str, Any]] = {}
    if release and returned_tag != RELEASE_TAG:
        errors.append(f"explicit release tag mismatch: expected={RELEASE_TAG!r} got={returned_tag!r}")
    for asset in release.get("assets") or ():
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if name not in REQUIRED_ASSETS:
            continue
        found[name] = {
            "name": name,
            "tag": returned_tag,
            "release_id": release.get("id"),
            "release_name": release.get("name"),
            "release_draft": bool(release.get("draft")),
            "release_prerelease": bool(release.get("prerelease")),
            "asset_id": asset.get("id"),
            "size": int(asset.get("size") or 0),
            "digest": str(asset.get("digest") or ""),
            "state": asset.get("state"),
            "created_at": asset.get("created_at"),
            "updated_at": asset.get("updated_at"),
            "browser_download_url": asset.get("browser_download_url"),
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
        "required": list(REQUIRED_ASSETS),
        "found": found,
        "missing": [name for name in REQUIRED_ASSETS if name not in found],
        "errors": errors,
        "release_count_scanned": 1 if release else 0,
    }
    _write_json(artifact_dir / "release-assets.json", release_payload)

    download_log: list[str] = []
    verification: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_ASSETS:
        meta = found.get(name)
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
                download_log.append(f"[{name}] tag={RELEASE_TAG} success={ok}\n{output}")
                row["download_command_success"] = ok
                if not ok:
                    row["download_error"] = output[-4000:]
            except (OSError, subprocess.SubprocessError) as exc:
                row["download_command_success"] = False
                row["download_error"] = repr(exc)

        row["exists"] = target.is_file()
        row["actual_size"] = target.stat().st_size if target.is_file() else 0
        row["sha256"] = _sha256(target) if target.is_file() else ""
        expected_digest = row["release_digest"].lower()
        expected_hash = expected_digest.split(":", 1)[1] if expected_digest.startswith("sha256:") else ""
        row["size_verified"] = bool(row["expected_size"] > 0 and row["actual_size"] == row["expected_size"])
        row["hash_verified"] = bool(expected_hash and row["sha256"] == expected_hash)
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
        row["verified"] = bool(
            row["release_found"]
            and row["download_complete"]
            and row["hash_verified"]
        )
        verification[name] = row

    (artifact_dir / "corpus-download.log").write_text("\n\n".join(download_log), encoding="utf-8")
    all_verified = all(verification[name]["verified"] for name in REQUIRED_ASSETS)
    _write_json(
        artifact_dir / "corpus-download-verification.json",
        {
            "requested_tag": RELEASE_TAG,
            "all_verified": all_verified,
            "assets": verification,
            "errors": errors,
        },
    )

    zip1 = corpus_dir / "Downloads(1)(1).zip"
    zip2 = corpus_dir / "Downloads(2)(1).zip"
    publish = corpus_dir / "publish_repository.zip"
    standalone_zip = corpus_dir / "standalone-images.zip"
    (artifact_dir / "corpus-paths.txt").write_text(
        f"zip1={zip1}\nzip2={zip2}\npublish_repository={publish}\nstandalone_zip={standalone_zip}\n",
        encoding="utf-8",
    )

    rich_available = bool(all_verified and zip1.is_file() and zip2.is_file())
    product_db = ""
    standalone_dir = corpus_dir / "standalone"
    standalone_count = 0
    if all_verified:
        try:
            publish_dir = corpus_dir / "publish"
            publish_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(publish) as archive:
                archive.extractall(publish_dir)
            db = next(publish_dir.rglob("atacado_historico.db"), None)
            product_db = str(db) if db else ""
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            errors.append(f"publish extract failed: {exc!r}")
        try:
            standalone_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(standalone_zip) as archive:
                archive.extractall(standalone_dir)
            standalone_count = sum(
                1
                for path in standalone_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            )
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            errors.append(f"standalone extract failed: {exc!r}")

    catalog_available = bool(product_db)
    standalone_available = standalone_count == 160
    _append_env("CORPUS_INTEGRITY_PASS", "true" if all_verified else "false")
    _append_env("RICH_CORPUS_AVAILABLE", "true" if rich_available else "false")
    _append_env("CATALOG_AVAILABLE", "true" if catalog_available else "false")
    _append_env("STANDALONE_AVAILABLE", "true" if standalone_available else "false")
    if product_db:
        _append_env("PRODUCT_DB", product_db)
    if standalone_available:
        _append_env("STANDALONE_DIR", str(standalone_dir))

    if standalone_dir.exists():
        (artifact_dir / "standalone-files.txt").write_text(
            "\n".join(str(path) for path in sorted(standalone_dir.rglob("*")) if path.is_file()),
            encoding="utf-8",
        )
    (artifact_dir / "standalone-count.txt").write_text(str(standalone_count), encoding="utf-8")

    availability = {
        "requested_release_tag": RELEASE_TAG,
        "corpus_integrity_pass": all_verified,
        "rich_corpus_available": rich_available,
        "catalog_available": catalog_available,
        "standalone_available": standalone_available,
        "standalone_count": standalone_count,
        "product_db": product_db,
        "release_assets": release_payload,
        "verification": verification,
        "expected": {
            "pptx": 36,
            "slides": 566,
            "embedded_unique": 1910,
            "media_occurrences": 2324,
            "standalone": 160,
            "catalog": 520,
        },
        "errors": errors,
    }
    _write_json(artifact_dir / "corpus-availability.json", availability)
    print(json.dumps(availability, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
