from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

_SLIDE_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")

EXPECTED = {
    "pptx": 36,
    "slides": 566,
    "media_file_occurrences": 2324,
    "unique_media_exact": 1910,
}


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def scan(root: Path) -> dict:
    pptx_files = sorted(root.rglob("*.pptx"))
    slide_count = 0
    media_occurrences = 0
    media_hashes: set[str] = set()
    file_rows: list[dict] = []
    errors: list[str] = []

    for path in pptx_files:
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                slides = [name for name in names if _SLIDE_RE.match(name)]
                media = [name for name in names if name.startswith("ppt/media/") and not name.endswith("/")]
                slide_count += len(slides)
                media_occurrences += len(media)
                local_hashes: set[str] = set()
                for name in media:
                    digest = _sha256(archive.read(name))
                    media_hashes.add(digest)
                    local_hashes.add(digest)
                file_rows.append(
                    {
                        "path": str(path),
                        "slides": len(slides),
                        "media_file_occurrences": len(media),
                        "unique_media_exact_in_file": len(local_hashes),
                    }
                )
        except Exception as exc:  # evidence collector: retain exact failure, do not hide it
            errors.append(f"{path}: {exc!r}")

    metrics = {
        "files_found": len(pptx_files),
        "slides": slide_count,
        "media_file_occurrences": media_occurrences,
        "unique_media_exact": len(media_hashes),
    }
    checks = {
        "pptx": metrics["files_found"] == EXPECTED["pptx"],
        "slides": metrics["slides"] == EXPECTED["slides"],
        "media_file_occurrences": metrics["media_file_occurrences"] == EXPECTED["media_file_occurrences"],
        "unique_media_exact": metrics["unique_media_exact"] == EXPECTED["unique_media_exact"],
        "no_scan_errors": not errors,
    }
    return {
        "measurement_semantics": {
            "media_file_occurrences": "sum of ppt/media package entries across the 36 extracted PPTX documents",
            "unique_media_exact": "global unique SHA-256 values of ppt/media package entries",
            "note": "This intentionally does not equate slide image/blip references with package media occurrences.",
        },
        "metrics": metrics,
        "expected": EXPECTED,
        "checks": checks,
        "pass": all(checks.values()),
        "errors": errors,
        "files": file_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Phase 3A rich corpus against the measured package-level baseline.")
    parser.add_argument("root", help="Directory containing the extracted PPTX files produced by the real corpus trainer")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    payload = scan(Path(args.root))
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["pass"] else 11


if __name__ == "__main__":
    raise SystemExit(main())
