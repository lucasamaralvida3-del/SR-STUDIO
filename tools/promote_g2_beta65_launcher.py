#!/usr/bin/env python3
"""Prepare an existing certified G2 Beta65 Windows release for the legacy launcher.

This is intentionally a separate compatibility artifact. The already published
standalone Beta65 ZIP, release tag, Beta43 and Stable are never overwritten.
The caller must verify/upload the resulting ZIP before publishing the manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

VERSION = "5.0.0-hybrid.g2beta.65"
SOURCE_COMMIT = __import__("os").environ.get("GITHUB_SHA", "")
ASSET = "SR_STUDIO_G2_BETA_65_LAUNCHER_BUNDLE.zip"
REPO = "lucasamaralvida3-del/SR-STUDIO"
URL = f"https://github.com/{REPO}/releases/download/g2-beta-65/{ASSET}"
REQUIRED = {
    "SR Studio 5.exe",
    "Graphics2Host/SRGraphicsEngine2Host.exe",
    "Graphics2Host/_internal/srstudio/graphics2/qml/GraphicsEditor.qml",
    "Graphics2Host/_internal/srstudio/graphics2/qml/SceneImage.qml",
    "Graphics2Host/_internal/srstudio/assets/campaigns/catalog.json",
}


def sha256_file(path: Path) -> str:
    result = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def safe_member(path: str) -> str:
    """Reject zip-slip, symlinks are rejected separately via mode bits."""
    value = path.replace("\\", "/")
    bits = PurePosixPath(value).parts
    if not value or value.startswith("/") or "\x00" in value or ":" in value or ".." in bits or "." in bits or "//" in value:
        raise ValueError(f"Unsafe release path: {path!r}")
    return value


def prepare(source: Path, target: Path, existing_manifest: Path, result_manifest: Path) -> dict:
    base = json.loads(existing_manifest.read_text(encoding="utf-8-sig"))
    if base.get("channel") != "beta" or base.get("version") != "5.0.0-hybrid.g2beta.64":
        raise ValueError("Beta channel must currently point to Beta62; refusing to overwrite a newer release")
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source, "r") as previous, ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=3, allowZip64=True) as out:
        members = {safe_member(x.filename): x for x in previous.infolist() if not x.is_dir()}
        if not REQUIRED.issubset(members):
            raise ValueError(f"Required Beta65 program files absent: {sorted(REQUIRED - set(members))}")
        if len(members) != sum(not x.is_dir() for x in previous.infolist()):
            raise ValueError("Duplicate archive names")
        # The built-in promotion gallery must truly be present in the Windows
        # launcher payload. Reject a build with missing/corrupt logos or thumbs.
        base_path = "Graphics2Host/_internal/srstudio/assets/campaigns/"
        catalog = json.loads(previous.read(base_path + "catalog.json"))
        if catalog.get("format") != "SRSTUDIO_BUILTIN_CAMPAIGN_ART_1":
            raise ValueError("Beta65 built-in artwork catalog missing or incompatible")
        assets = catalog.get("assets", [])
        if (len(assets) != 12 or
                sum(a.get("kind") == "background" for a in assets) != 4 or
                sum(a.get("kind") == "seal" for a in assets) != 8):
            raise ValueError("Beta65 must ship 4 backgrounds and 8 promotional logos")
        for item in assets:
            for path_key, size_key, hash_key in (
                ("path", "size", "sha256"),
                ("thumbnail", "thumbnail_size", "thumbnail_sha256")):
                relative = safe_member(str(item[path_key]))
                full = base_path + relative
                if full not in members:
                    raise ValueError(f"Missing built-in campaign image: {full}")
                image = previous.read(full)
                if len(image) != item[size_key] or sha256(image).hexdigest() != item[hash_key]:
                    raise ValueError(f"Corrupt built-in campaign image: {full}")
        for name, member in members.items():
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Archive symlink not supported: {name}")
            with previous.open(member) as file_in, out.open("files/SRStudio5/" + name, "w", force_zip64=True) as file_out:
                shutil.copyfileobj(file_in, file_out, length=4 * 1024 * 1024)
        out.writestr("files/VERSAO.txt", "G2 BETA 65\n")
        out.writestr("files/version.json", json.dumps({
            "version": VERSION,
            "release": "g2-beta-65",
            "source_commit": SOURCE_COMMIT,
            "entrypoint": "SRStudio5/SR Studio 5.exe",
        }, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(target, "r") as generated:
        actual = set(generated.namelist())
        if not all("files/SRStudio5/" + name in actual for name in REQUIRED):
            raise AssertionError("Launcher ZIP structure verification failed")
        if "files/version.json" not in actual or generated.testzip() is not None:
            raise AssertionError("Launcher ZIP content verification failed")
    size = target.stat().st_size
    digest = sha256_file(target)
    manifest = {
        "format": "SRSTUDIO_HYBRID_BUNDLE_1",
        "product": "SR Studio",
        "channel": "beta",
        "version": VERSION,
        "product_version": "5.0.0",
        "release_label": "G2 Beta 65 - Correções iniciais dos encartes, cards, miniaturas e PNG",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "min_launcher": base.get("min_launcher", "4.0.1-hybrid.base2.6"),
        "min_launcher_version": base.get("min_launcher_version", "4.0.1-hybrid.base2.6"),
        "bundle": {"url": URL, "sha256": digest, "size": size, "member_prefix": "files/"},
        "url": URL,
        "bundle_url": URL,
        "sha256": digest,
        "size": size,
        "member_prefix": "files/",
        "previous_version": base["version"],
        "entrypoint": "SRStudio5/SR Studio 5.exe",
        "graphics2_test": True,
        "graphics2_primary": True,
        "launcher_path_safe": True,
        "source_commit": SOURCE_COMMIT,
        "public_asset_verified": True,
        "tag": "g2-beta-65",
        "asset": ASSET,
        "notes": "Beta 65: primeira rodada de correções visuais no editor: cards responsivos com +, − e estrela, miniaturas de páginas, aviso de fotos ausentes, remoção de fundo da foto selecionada e reserva por conteúdo visível do selo. Alguns refinamentos visuais ainda estão pendentes. Stable intacta.",
    }
    result_manifest.parent.mkdir(parents=True, exist_ok=True)
    result_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared launcher bundle: {size} bytes, sha256={digest}")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--bundle-output", type=Path, required=True)
    p.add_argument("--existing-manifest", type=Path, required=True)
    p.add_argument("--manifest-output", type=Path, required=True)
    args = p.parse_args()
    prepare(args.input, args.bundle_output, args.existing_manifest, args.manifest_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
