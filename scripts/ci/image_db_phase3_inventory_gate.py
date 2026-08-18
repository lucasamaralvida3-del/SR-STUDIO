from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
EXPECTED = {
    "pptx": 36,
    "slides": 566,
    "media_occurrences": 2324,
    "embedded_unique": 1910,
}


def scan_archives(paths: list[Path]) -> dict:
    pptx_count = 0
    slide_count = 0
    media_occurrences = 0
    media_hashes: set[str] = set()
    pptx_hashes: set[str] = set()
    files: list[dict] = []
    errors: list[str] = []

    for outer_path in paths:
        try:
            with zipfile.ZipFile(outer_path) as outer:
                members = [
                    info
                    for info in outer.infolist()
                    if not info.is_dir() and info.filename.lower().endswith(".pptx")
                ]
                for info in members:
                    try:
                        blob = outer.read(info)
                        pptx_sha = hashlib.sha256(blob).hexdigest()
                        pptx_hashes.add(pptx_sha)
                        pptx_count += 1
                        with zipfile.ZipFile(io.BytesIO(blob)) as presentation:
                            names = [name for name in presentation.namelist() if not name.endswith("/")]
                            slides = sum(1 for name in names if SLIDE_RE.match(name))
                            media_names = [name for name in names if name.startswith("ppt/media/")]
                            slide_count += slides
                            media_occurrences += len(media_names)
                            for media_name in media_names:
                                media_hashes.add(hashlib.sha256(presentation.read(media_name)).hexdigest())
                        files.append(
                            {
                                "archive": outer_path.name,
                                "member": info.filename,
                                "pptx_sha256": pptx_sha,
                                "slides": slides,
                                "media_occurrences": len(media_names),
                            }
                        )
                    except Exception as exc:  # evidence gate: record exact member failure
                        errors.append(f"{outer_path.name}!{info.filename}: {type(exc).__name__}: {exc}")
        except Exception as exc:
            errors.append(f"{outer_path}: {type(exc).__name__}: {exc}")

    measured = {
        "pptx": pptx_count,
        "unique_pptx_exact": len(pptx_hashes),
        "slides": slide_count,
        "media_occurrences": media_occurrences,
        "embedded_unique": len(media_hashes),
    }
    checks = {key: measured[key] == value for key, value in EXPECTED.items()}
    return {
        "measurement_semantics": {
            "media_occurrences": "sum of physical ppt/media members across the 36 PPTX packages",
            "embedded_unique": "global exact SHA-256 uniqueness across physical ppt/media members",
            "note": "raw slide relationship/blip references are intentionally not used for the 2,324 baseline",
        },
        "measured": measured,
        "expected": EXPECTED,
        "checks": checks,
        "errors": errors,
        "files": files,
        "pass": not errors and all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate exact Phase 3A rich-corpus package baseline.")
    parser.add_argument("archives", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = scan_archives([Path(value) for value in args.archives])
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["measured"], ensure_ascii=False))
    return 0 if payload["pass"] else 11


if __name__ == "__main__":
    raise SystemExit(main())
