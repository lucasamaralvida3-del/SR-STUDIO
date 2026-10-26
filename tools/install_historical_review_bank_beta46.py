from __future__ import annotations

"""Install the *review-only* recovered GitHub corpus into the existing SR bank.

Absolute asset paths in GitHub Actions artifacts are intentionally discarded.
No image becomes an accepted product association during this installation.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from srstudio.images.library import ImageLibrary

_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
_HEX24 = re.compile(r"^[0-9a-f]{24}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def install_review_bank(source: str | Path, destination: str | Path) -> dict:
    source = Path(source)
    index = json.loads((source / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict):
        raise ValueError("Índice histórico inválido")
    library = ImageLibrary(destination)
    installed = existing = 0
    # Verify the WHOLE incoming archive before changing the persistent bank.
    candidates = []
    for key, row in index.items():
        if not isinstance(row, dict) or not _HEX24.fullmatch(str(key)):
            raise ValueError("Identificador inválido no banco recuperado")
        if row.get("review_status") != "pending" or row.get("kind") not in ("unknown", "product"):
            raise ValueError("Artefato contém associação já aprovada ou estado não permitido")
        meta = row.get("metadata") or {}
        if not isinstance(meta, dict) or not meta.get("requires_manual_approval"):
            raise ValueError("Registro sem obrigação explícita de revisão")
        sha = str(meta.get("original_file_sha256") or "").lower()
        if not _HEX64.fullmatch(sha):
            raise ValueError("Checksum histórico ausente")
        suffix = Path(str(row.get("path") or "")).suffix.lower()
        if suffix not in _EXTENSIONS:
            raise ValueError("Formato de imagem recuperada não autorizado")
        file = source / "assets" / (str(key) + suffix)
        if not file.is_file() or file.is_symlink():
            raise ValueError("Arquivo de imagem recuperada ausente ou inválido")
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != sha or not digest.startswith(str(key)):
            raise ValueError("Integridade da imagem recuperada não confere")
        candidates.append((key, file, row, meta))
    known = {a.id: a for a in library.all()}
    for key, file, row, meta in candidates:
        if key in known:
            existing += 1
            continue
        library.import_image(
            file,
            product_name="",
            product_key="",
            kind="unknown",
            confidence=0.0,
            review_status="pending",
            source_kind="legacy-github-corpus",
            source_file=str(row.get("source_file") or row.get("original_name") or ""),
            metadata=dict(meta),
        )
        installed += 1
    return {
        "available": len(candidates), "installed_pending": installed,
        "already_present": existing, "auto_approved": 0,
        "manual_review_required": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True,
                        help="Pasta extraída do artefato de revisão do GitHub")
    parser.add_argument("--destination", type=Path,
                        default=Path.home() / ".srstudio5" / "images")
    args = parser.parse_args()
    print(json.dumps(install_review_bank(args.source, args.destination),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
