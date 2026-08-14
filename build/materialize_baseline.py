from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

BASELINE_VERSION = "4.0.16-hybrid.stable4"
BASELINE_SHA256 = "4ac83d3e1a704caab3c77ae21270d74bbe56182d9b22c7ae1b445f83a30089d6"
MEMBER_PREFIX = "files/"
EXPECTED_FILES = 65

REQUIRED = {
    "SR_Studio_Gerador.py",
    "AtacadoModule.py",
    "ManualModule.py",
    "Encartes10_beta16.js",
    "SRSpellCheck.py",
    "assets/SR_logo.png",
    "assets/SR_Studio.ico",
    "modelos/ATACADO.pptx",
    "version.json",
    "requirements.txt",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def materialize(zip_path: Path, destination: Path) -> dict:
    if sha256(zip_path) != BASELINE_SHA256:
        raise RuntimeError("SHA-256 da Stable 4 não confere")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    extracted: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name.startswith(MEMBER_PREFIX):
                continue
            rel = name[len(MEMBER_PREFIX):].strip("/")
            if not rel:
                continue
            target = destination / Path(rel)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(rel)

    extracted_set = set(extracted)
    missing = sorted(REQUIRED - extracted_set)
    if missing:
        raise RuntimeError("Arquivos obrigatórios ausentes: " + ", ".join(missing))
    if len(extracted) != EXPECTED_FILES:
        raise RuntimeError(f"Quantidade de arquivos inesperada: {len(extracted)}; esperado {EXPECTED_FILES}")

    version_path = destination / "version.json"
    version = json.loads(version_path.read_text(encoding="utf-8-sig"))
    dist = str(version.get("distribution_version") or version.get("version") or "")
    if dist != BASELINE_VERSION:
        raise RuntimeError(f"Baseline incorreta: {dist!r}")

    for cache in destination.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
    for compiled in list(destination.rglob("*.pyc")) + list(destination.rglob("*.pyo")):
        compiled.unlink(missing_ok=True)

    return {
        "format": "SRSTUDIO_NEXT_FOUNDATION_1",
        "target_major": "5.0.0",
        "source_of_truth": destination.as_posix(),
        "baseline": BASELINE_VERSION,
        "baseline_tag": "v4.0.16-hybrid.stable4",
        "baseline_sha256": BASELINE_SHA256,
        "canonical_file_count": len(extracted),
        "status": "foundation",
        "public_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--metadata", type=Path, default=Path("build/foundation.json"))
    args = parser.parse_args()

    metadata = materialize(args.zip_path, args.destination)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Base canônica materializada: {metadata['canonical_file_count']} arquivos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
