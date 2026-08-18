from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _canonical_sha(data: dict[str, Any]) -> str:
    metadata = dict(data.get("metadata") or {})
    value = str(metadata.get("sha256_full") or metadata.get("sha256") or "").strip().lower()
    return value if len(value) == 64 else ""


def restore(args: argparse.Namespace) -> int:
    source_index = Path(args.index_source)
    library_root = Path(args.library)
    output = Path(args.output)
    library_root.mkdir(parents=True, exist_ok=True)
    assets_dir = library_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(source_index.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Phase 3A persisted index must be a JSON object")

    wanted: dict[str, list[tuple[str, str]]] = {}
    missing_hash_assets: list[str] = []
    for asset_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        sha = _canonical_sha(raw)
        if not sha:
            missing_hash_assets.append(str(asset_id))
            continue
        old_path = Path(str(raw.get("path") or ""))
        suffix = old_path.suffix or Path(str(raw.get("original_name") or "")).suffix or ".png"
        target = assets_dir / f"{asset_id}{suffix.lower()}"
        raw["path"] = str(target)
        wanted.setdefault(sha, []).append((str(asset_id), str(target)))

    (library_root / "index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    restored_sha: set[str] = set()
    scanned_pptx = 0
    scanned_media = 0
    corrupt_pptx: list[str] = []

    for archive_path_text in args.archive:
        archive_path = Path(archive_path_text)
        with zipfile.ZipFile(archive_path) as outer:
            for outer_name in outer.namelist():
                if not outer_name.lower().endswith(".pptx"):
                    continue
                scanned_pptx += 1
                try:
                    pptx_bytes = outer.read(outer_name)
                    with zipfile.ZipFile(io.BytesIO(pptx_bytes)) as pptx:
                        for member in pptx.namelist():
                            normalized = member.replace("\\", "/").lower()
                            if "/media/" not in normalized or member.endswith("/"):
                                continue
                            scanned_media += 1
                            data = pptx.read(member)
                            sha = _sha256_bytes(data)
                            targets = wanted.get(sha)
                            if not targets or sha in restored_sha:
                                continue
                            for _, target_text in targets:
                                target = Path(target_text)
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(data)
                            restored_sha.add(sha)
                except (OSError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
                    corrupt_pptx.append(f"{archive_path.name}:{outer_name}:{exc!r}")

    missing: list[dict[str, Any]] = []
    physical = 0
    hash_mismatch: list[str] = []
    for asset_id, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        target = Path(str(raw.get("path") or ""))
        sha = _canonical_sha(raw)
        if not target.is_file():
            missing.append({"asset_id": str(asset_id), "sha256": sha, "target": str(target)})
            continue
        physical += 1
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if sha and actual != sha:
            hash_mismatch.append(str(asset_id))

    report = {
        "method": "materialize persisted Phase 3A index from exact embedded PPTX media; no training/association ingestion executed",
        "canonical_index_entries": len(payload),
        "physical_materialized": physical,
        "unique_sha_requested": len(wanted),
        "unique_sha_restored": len(restored_sha),
        "scanned_pptx": scanned_pptx,
        "scanned_media_entries": scanned_media,
        "assets_without_canonical_sha": missing_hash_assets,
        "missing_assets": missing,
        "hash_mismatch_assets": hash_mismatch,
        "corrupt_pptx": corrupt_pptx,
    }
    report["pass"] = bool(
        len(payload) == 1036
        and physical == 1036
        and not missing_hash_assets
        and not missing
        and not hash_mismatch
        and not corrupt_pptx
    )
    _write_json(output, report)
    return 0 if report["pass"] else 51


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize a persisted Phase 3A image library without re-running corpus training.")
    parser.add_argument("--index-source", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--archive", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    return restore(args)


if __name__ == "__main__":
    raise SystemExit(main())
