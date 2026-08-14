from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "sr_studio"


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def build(version: str, channel: str, release_label: str, output: Path) -> dict:
    if channel not in {"beta", "stable"}:
        raise ValueError("channel deve ser beta ou stable")
    if not SOURCE.exists():
        raise RuntimeError("Fonte canônica ausente")

    with tempfile.TemporaryDirectory(prefix="srstudio5-build-") as td:
        work = Path(td) / "files"
        shutil.copytree(
            SOURCE,
            work,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )

        version_path = work / "version.json"
        try:
            current = json.loads(version_path.read_text(encoding="utf-8-sig"))
        except Exception:
            current = {}

        current.update(
            {
                "product_version": version.split("-", 1)[0],
                "version": version,
                "distribution_version": version,
                "channel": channel,
                "release_label": release_label,
                "built_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        write_text(version_path, json.dumps(current, ensure_ascii=False, indent=2) + "\n")
        write_text(work / "SRStudioVersion.txt", version + "\n")
        write_text(work / "VERSAO.txt", f"SR Studio {version.split('-', 1)[0]} • {release_label}\n")

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(work.rglob("*")):
                if path.is_file():
                    arc = Path("files") / path.relative_to(work)
                    zf.write(path, arc.as_posix())

    h = hashlib.sha256()
    with output.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {
        "file": output.name,
        "version": version,
        "channel": channel,
        "release_label": release_label,
        "sha256": h.hexdigest(),
        "size": output.stat().st_size,
        "member_prefix": "files/",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Empacotador canônico do SR Studio")
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=["beta", "stable"], required=True)
    parser.add_argument("--release-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()

    info = build(args.version, args.channel, args.release_label, args.output)
    if args.metadata:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        write_text(args.metadata, json.dumps(info, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
