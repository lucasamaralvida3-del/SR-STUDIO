from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REQUIRED_ASSETS = (
    "Downloads(1)(1).zip",
    "Downloads(2)(1).zip",
    "publish_repository.zip",
    "standalone-images.zip",
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def _request_json(url: str, token: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "srstudio-image-db-phase3-ci",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


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


def _download_with_gh(tag: str, name: str, target_dir: Path, token: str) -> tuple[bool, str]:
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    completed = subprocess.run(
        ["gh", "release", "download", tag, "-p", name, "-D", str(target_dir), "--clobber"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        timeout=600,
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
    releases: list[dict[str, Any]] = []
    if not repository or not token:
        errors.append("GITHUB_REPOSITORY/GITHUB_TOKEN unavailable")
    else:
        try:
            page = 1
            while True:
                payload = _request_json(
                    f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}",
                    token,
                )
                if not isinstance(payload, list) or not payload:
                    break
                releases.extend(item for item in payload if isinstance(item, dict))
                if len(payload) < 100:
                    break
                page += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"release listing failed: {exc!r}")

    found: dict[str, dict[str, Any]] = {}
    for release in releases:
        tag = str(release.get("tag_name") or "")
        for asset in release.get("assets") or ():
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            if name not in REQUIRED_ASSETS or name in found:
                continue
            found[name] = {
                "name": name,
                "tag": tag,
                "release_id": release.get("id"),
                "release_draft": bool(release.get("draft")),
                "release_prerelease": bool(release.get("prerelease")),
                "asset_id": asset.get("id"),
                "size": int(asset.get("size") or 0),
                "digest": str(asset.get("digest") or ""),
                "state": asset.get("state"),
                "created_at": asset.get("created_at"),
                "updated_at": asset.get("updated_at"),
            }

    release_payload = {
        "required": list(REQUIRED_ASSETS),
        "found": found,
        "missing": [name for name in REQUIRED_ASSETS if name not in found],
        "errors": errors,
        "release_count_scanned": len(releases),
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
            "path": str(target),
            "expected_size": int((meta or {}).get("size") or 0),
            "release_digest": str((meta or {}).get("digest") or ""),
            "tag": str((meta or {}).get("tag") or ""),
            "release_draft": bool((meta or {}).get("release_draft")),
        }
        if meta and meta.get("tag"):
            try:
                ok, output = _download_with_gh(str(meta["tag"]), name, corpus_dir, token)
                download_log.append(f"[{name}] tag={meta['tag']} success={ok}\n{output}")
                if not ok:
                    row["download_error"] = output[-4000:]
            except (OSError, subprocess.SubprocessError) as exc:
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
        row["verified"] = bool(
            row["release_found"]
            and row["exists"]
            and row["size_verified"]
            and row["hash_verified"]
            and row["zip_integrity"]
        )
        verification[name] = row

    (artifact_dir / "corpus-download.log").write_text("\n\n".join(download_log), encoding="utf-8")
    all_verified = all(verification[name]["verified"] for name in REQUIRED_ASSETS)
    _write_json(
        artifact_dir / "corpus-download-verification.json",
        {"all_verified": all_verified, "assets": verification, "errors": errors},
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
                1 for path in standalone_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
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
