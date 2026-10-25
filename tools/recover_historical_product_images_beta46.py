from __future__ import annotations

"""Stage verified historical SR product pictures for *manual* image-bank review.

This is a data-recovery utility, not an approval engine. It never invents SKU,
EAN, brand, name or approvals from filenames. Reads ZIP members directly
without writing their untrusted paths, validates the historical SHA-256
manifest and exports a deterministic review-only ImageLibrary directory.
"""

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from srstudio.images.library import ImageLibrary

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
MAX_MEMBER_BYTES = 50 * 1024 * 1024
MAX_CANDIDATES = 10000


def recover_standalone_images(
    archive: str | Path,
    manifest: str | Path,
    destination: str | Path,
    *,
    expected_archive_sha256: str = "",
) -> dict:
    source = Path(archive)
    manifest_obj = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if manifest_obj.get("release_tag") != "image-db-corpus-v1":
        raise ValueError("Manifesto histórico não corresponde ao release auditado")
    reference = manifest_obj.get("asset") or {}
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    actual = digest.hexdigest()
    expected = str(expected_archive_sha256 or reference.get("sha256") or "").strip().lower()
    if len(expected) != 64 or expected != actual:
        raise ValueError("SHA-256 do arquivo standalone-images.zip não confere")
    records = manifest_obj.get("images")
    if not isinstance(records, list) or len(records) > MAX_CANDIDATES:
        raise ValueError("Lista de imagens histórica inválida ou grande demais")

    output = Path(destination)
    # Fail before writing the first image on a manifest with bad metadata.
    seen = set()
    for row in records:
        name = row.get("filename")
        sha = str(row.get("sha256") or "").lower()
        if (not isinstance(name, str) or not name or name in seen
                or len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha)):
            raise ValueError("Manifesto de imagens contém entradas inválidas")
        seen.add(name)

    image_bank = ImageLibrary(output)
    created = skipped = rejected = 0
    with zipfile.ZipFile(source) as packed:
        for row in records:
            if not row.get("valid"):
                rejected += 1
                continue
            if row.get("classification") != "candidate":
                rejected += 1  # Decorative art must not become a product.
                continue
            name = str(row["filename"])
            suffix = Path(name).suffix.lower()
            if suffix not in SUPPORTED:
                rejected += 1
                continue
            zip_member = str((row.get("provenance") or {}).get("zip_member") or name)
            try:
                member = packed.getinfo(zip_member)
            except KeyError as exc:
                raise ValueError(f"Imagem ausente do pacote: {name}") from exc
            if member.is_dir() or member.file_size <= 0 or member.file_size > MAX_MEMBER_BYTES:
                raise ValueError(f"Tamanho de imagem inválido: {name}")
            with tempfile.TemporaryDirectory(prefix="sr-image-recovery-") as temp:
                dest = Path(temp) / ("verified" + suffix)
                check = hashlib.sha256()
                count = 0
                with packed.open(member) as source_file, dest.open("wb") as target:
                    for block in iter(lambda: source_file.read(1024 * 1024), b""):
                        count += len(block)
                        if count > MAX_MEMBER_BYTES:
                            raise ValueError("Imagem maior que o limite seguro")
                        check.update(block)
                        target.write(block)
                if check.hexdigest() != str(row["sha256"]).lower():
                    raise ValueError(f"SHA-256 de imagem inválido: {name}")
                existing = {asset.id for asset in image_bank.all()}
                imported = image_bank.import_image(
                    dest,
                    product_key="",
                    product_name="",
                    kind="unknown",
                    confidence=0.0,
                    review_status="pending",
                    source_kind="legacy-github-corpus",
                    source_file=name,
                    metadata={
                        "archive_release": "image-db-corpus-v1",
                        "archive_asset": str(reference.get("name") or "standalone-images.zip"),
                        "archive_member": zip_member,
                        "archive_sha256": actual,
                        "original_file_sha256": check.hexdigest(),
                        "legacy_classification": "unreviewed-product-candidate",
                        "requires_manual_approval": True,
                    },
                )
                if imported.id in existing:
                    skipped += 1
                else:
                    created += 1

    stats = image_bank.stats()
    report = {
        "release": "image-db-corpus-v1",
        "archive_sha256": actual,
        "record_count": len(records),
        "imported": created,
        "duplicates": skipped,
        "rejected_decorative_or_invalid": rejected,
        "accepted_automatically": 0,
        "image_bank": stats,
        "requires_manual_review": True,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "recovery-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Recuperar imagens históricas em estado pendente, sem aprovar correspondências")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--sha256", default="")
    args = parser.parse_args()
    print(json.dumps(
        recover_standalone_images(
            args.archive, args.manifest, args.destination, expected_archive_sha256=args.sha256
        ), ensure_ascii=False, indent=2
    ))


if __name__ == "__main__":
    main()
