from __future__ import annotations

"""Import the Beta46 historic *review-only* ZIP into the original local SR bank.

Never approve a recovered picture automatically. Validate every member and
checksum before writing anything into the existing ImageLibrary.
"""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import json
import re

from srstudio.images.library import ImageLibrary

_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
_KEY = re.compile(r"^[0-9a-f]{24}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARCHIVE_ENTRIES = 2500
_MAX_INDEX_BYTES = 12 * 1024 * 1024
_MAX_IMAGE_BYTES = 50 * 1024 * 1024


def import_historical_review_zip(archive: str | Path, *,
                                 destination: Path | None = None) -> dict:
    from .legacy_image_bank_bridge import image_bank_root

    archive = Path(archive).expanduser()
    dest = Path(destination) if destination is not None else image_bank_root()
    with ZipFile(archive, "r") as zipped:
        members = zipped.infolist()
        if len(members) > _MAX_ARCHIVE_ENTRIES:
            raise ValueError("Arquivo histórico possui entradas demais.")
        names = [entry.filename for entry in members]
        if len(names) != len(set(names)) or "index.json" not in names:
            raise ValueError("ZIP histórico sem índice ou com entradas duplicadas.")
        for member in members:
            name = member.filename
            if (name.startswith("/") or "\\" in name or ".." in name.split("/")
                    or ":" in name or (member.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Caminho inseguro no ZIP histórico.")
            if not member.is_dir() and not (
                name == "index.json" or name.startswith("assets/") or
                name in {"recovery-report.json", "REVIEW_FIRST.txt"}
            ):
                raise ValueError("Conteúdo inesperado no ZIP histórico.")
        index_info = zipped.getinfo("index.json")
        if index_info.file_size > _MAX_INDEX_BYTES:
            raise ValueError("Índice histórico grande demais.")
        index = json.loads(zipped.read("index.json"))
        if not isinstance(index, dict) or len(index) > 1000:
            raise ValueError("Índice histórico inválido.")
        with TemporaryDirectory(prefix="sr-image-review-") as temp:
            work = Path(temp)
            entries = []
            # VERIFY the complete archive before modifying the persistent bank.
            for key, row in index.items():
                if not _KEY.fullmatch(str(key)) or not isinstance(row, dict):
                    raise ValueError("Registro histórico inválido.")
                if row.get("review_status") != "pending" or row.get("kind") not in ("product", "unknown"):
                    raise ValueError("Arquivo histórico tenta aprovar imagem sem revisão.")
                metadata = row.get("metadata") or {}
                if not isinstance(metadata, dict) or not metadata.get("requires_manual_approval"):
                    raise ValueError("Imagem histórica sem revisão obrigatória.")
                expected = str(metadata.get("original_file_sha256") or "").lower()
                if not _SHA.fullmatch(expected) or not expected.startswith(key):
                    raise ValueError("Assinatura da imagem histórica inválida.")
                suffix = Path(str(row.get("path") or "")).suffix.lower()
                if suffix not in _ALLOWED_EXT:
                    raise ValueError("Extensão histórica inválida.")
                member_name = f"assets/{key}{suffix}"
                try:
                    info = zipped.getinfo(member_name)
                except KeyError as exc:
                    raise ValueError(f"Imagem ausente no ZIP: {key}") from exc
                if info.file_size > _MAX_IMAGE_BYTES:
                    raise ValueError("Imagem histórica excede 50 MB.")
                target = work / f"{key}{suffix}"
                digest = sha256()
                with zipped.open(info) as source, target.open("wb") as output:
                    size = 0
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        size += len(chunk)
                        if size > _MAX_IMAGE_BYTES:
                            raise ValueError("Imagem histórica excede 50 MB.")
                        digest.update(chunk)
                        output.write(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError(f"Checksum histórico não confere: {key}")
                entries.append((key, target, row, metadata))

            library = ImageLibrary(dest)
            existing = {asset.id for asset in library.all()}
            installed = skipped = 0
            for key, file, row, metadata in entries:
                if key in existing:
                    skipped += 1
                    continue
                new = library.import_image(
                    file, product_name="", product_key="", kind="unknown",
                    confidence=0.0, review_status="pending",
                    source_kind="legacy-github-corpus",
                    source_file=str(row.get("source_file") or row.get("original_name") or ""),
                    metadata={**metadata,
                              "review_original_filename": str(row.get("original_name") or ""),
                              "review_source_file": str(row.get("source_file") or "")},
                )
                existing.add(new.id)
                installed += 1
            return {
                "available": len(entries), "installed_pending": installed,
                "already_present": skipped, "auto_approved": 0,
                "manual_review_required": True,
            }
