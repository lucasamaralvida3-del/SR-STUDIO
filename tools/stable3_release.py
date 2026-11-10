"""Create a verified launcher bundle for the Beta65-based Stable 3 build."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile


VERSION = "5.0.0-hybrid.stable3"
TAG = "v5.0.0-hybrid.stable3"
ASSET = "SR_STUDIO_5_0_0-hybrid_stable3_PROFESSIONAL.zip"
REPO = "lucasamaralvida3-del/SR-STUDIO"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
REQUIRED = (
    "SR Studio 5.exe",
    "Graphics2Host/SRGraphicsEngine2Host.exe",
    "Graphics2Host/_internal/srstudio/graphics2/qml/GraphicsEditor.qml",
)
SHIM = '''from __future__ import annotations
import os
import subprocess
from pathlib import Path

if __name__ == "__main__":
    app_dir = Path(__file__).resolve().parent
    exe = app_dir / "SRStudio5" / "SR Studio 5.exe"
    if not exe.is_file():
        raise FileNotFoundError(exe)
    env = os.environ.copy()
    env["SR_STUDIO_LAUNCHED_BY_UPDATER"] = "1"
    subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
'''


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_bundle(program: Path, archive: Path, previous: Path, output: Path, source_commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source_commit must be a 40-character Git SHA")
    old = json.loads(previous.read_text(encoding="utf-8-sig"))
    if old.get("channel") != "stable" or old.get("version") != "5.0.0-hybrid.stable2":
        raise ValueError("Expected current stable2 manifest; Stable may have advanced")
    for relative in REQUIRED:
        if not (program / relative).is_file():
            raise ValueError(f"Required program file missing: {relative}")
    files = sorted(path for path in program.rglob("*") if path.is_file())
    if not files or any(path.is_symlink() for path in files):
        raise ValueError("Empty or symlink-containing program directory")
    archive.parent.mkdir(parents=True, exist_ok=True)
    identity = {
        "version": VERSION,
        "product_version": "5.0.0",
        "channel": "stable",
        "release_label": "Stable 3 Professional",
        "entrypoint": "SR_Studio_Gerador.py",
        "professional_executable": "SRStudio5/SR Studio 5.exe",
        "promoted_from": "5.0.0-hybrid.g2beta.65",
        "source_commit": source_commit,
    }
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=3, allowZip64=True) as bundle:
        for path in files:
            relative = path.relative_to(program).as_posix()
            bundle.write(path, "files/SRStudio5/" + relative)
        bundle.writestr("files/SR_Studio_Gerador.py", SHIM)
        bundle.writestr("files/VERSAO.txt", "SR Studio 5.0.0 - Stable 3 Professional\n")
        bundle.writestr("files/version.json", json.dumps(identity, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        if not all("files/SRStudio5/" + name in names for name in REQUIRED):
            raise AssertionError("Stable bundle is missing a required executable or QML file")
        if bundle.testzip() is not None:
            raise AssertionError("Stable bundle failed CRC validation")
        if json.loads(bundle.read("files/version.json")) != identity:
            raise AssertionError("Stable bundle identity changed during packaging")
    digest = hash_file(archive)
    size = archive.stat().st_size
    manifest = {
        "format": "SRSTUDIO_HYBRID_BUNDLE_1",
        "product": "SR Studio",
        "channel": "stable",
        "version": VERSION,
        "product_version": "5.0.0",
        "release_label": "Stable 3 Professional",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "min_launcher": old.get("min_launcher", "4.0.1-hybrid.base3.4"),
        "min_launcher_version": old.get("min_launcher_version", "4.0.1-hybrid.base3.4"),
        "bundle": {"url": URL, "sha256": digest, "size": size, "member_prefix": "files/"},
        "url": URL,
        "bundle_url": URL,
        "sha256": digest,
        "size": size,
        "member_prefix": "files/",
        "previous_version": old["version"],
        "promoted_from": "5.0.0-hybrid.g2beta.65",
        "source_commit": source_commit,
        "entrypoint": "SR_Studio_Gerador.py",
        "graphics2_primary": True,
        "launcher_path_safe": True,
        "repair": old.get("repair", {"mode": "local_hash_catalog", "full_check_every_days": 7}),
        "delete": old.get("delete", []),
        "notes": "Beta 65 e modo noturno em toda a interface; cores dos encartes e exportações preservadas.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    result = build_bundle(args.program, args.archive, args.previous, args.output, args.source_commit)
    print(f"STABLE_BUNDLE size={result['size']} sha256={result['sha256']}")
