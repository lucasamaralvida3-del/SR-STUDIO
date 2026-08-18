import hashlib
import zipfile
from pathlib import Path
from types import SimpleNamespace

from srstudio.images.corpus_training import sha256_file
from srstudio.images.precision_training import PRECISION_TRAINER_VERSION, PrecisionProductImageCorpusTrainer


class EmptyImporter:
    def import_file(self, path, media_dir=None):
        return SimpleNamespace(slides=[], warnings=[])


class EmptyLibrary:
    def all(self):
        return []

    def update_metadata(self, *args, **kwargs):
        raise AssertionError("no assets should be updated in this test")


def _trainer(tmp_path: Path) -> PrecisionProductImageCorpusTrainer:
    return PrecisionProductImageCorpusTrainer(
        EmptyLibrary(),
        imports_root=tmp_path / "imports",
        importer=EmptyImporter(),
    )


def test_precision_policy_is_versioned_for_phase2_real_corpus():
    assert PRECISION_TRAINER_VERSION == "g2-image-precision-v3"


def test_archive_extraction_preserves_member_lineage_without_flattening_collision(tmp_path):
    archive_path = tmp_path / "downloads.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("folder-a/encarte.pptx", b"pptx-a")
        archive.writestr("folder-b/encarte.pptx", b"pptx-b")

    trainer = _trainer(tmp_path)
    warnings = []
    extracted = trainer._extract_zip_pptx(archive_path, warnings)

    assert warnings == []
    assert len(extracted) == 2
    assert extracted[0] != extracted[1]
    assert {path.name.split("__", 1)[1] for path in extracted} == {"encarte.pptx"}

    archive_sha = sha256_file(archive_path)
    for path in extracted:
        digest = sha256_file(path)
        rows = trainer._archive_provenance_by_pptx_sha[digest]
        assert len(rows) == 1
        row = rows[0]
        assert row["source_kind"] == "archive-pptx"
        assert row["source_archive_sha256"] == archive_sha
        assert row["source_member"].endswith("encarte.pptx")
        assert row["source_member_size"] == path.stat().st_size
        assert row["source_pptx_sha256"] == digest


def test_archive_provenance_reaches_incremental_record(tmp_path):
    archive_path = tmp_path / "downloads.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("campaign/TERCA VERDE.pptx", b"fake-package-for-importer")

    trainer = _trainer(tmp_path)
    extracted = trainer._extract_zip_pptx(archive_path, [])
    source = extracted[0]
    digest = sha256_file(source)

    record = trainer._process_pptx(source, digest)

    assert record["precision_trainer_version"] == "g2-image-precision-v3"
    assert len(record["source_provenance"]) == 1
    provenance = record["source_provenance"][0]
    assert provenance["source_archive"] == str(archive_path.resolve())
    assert provenance["source_member"] == "campaign/TERCA VERDE.pptx"
    assert provenance["source_pptx_sha256"] == digest


def test_duplicate_archive_observations_do_not_change_logical_document_fingerprint(tmp_path):
    trainer = _trainer(tmp_path)
    base_record = {
        "slides": 1,
        "raw_image_refs": 1,
        "image_sha256": ["a" * 64],
        "product_names": ["ARROZ PATOSUL 5KG"],
        "evidence": [
            {
                "source_slide": 1,
                "product_name": "ARROZ PATOSUL 5KG",
                "image_sha256": "a" * 64,
            }
        ],
    }
    with_archive_a = dict(base_record, source_provenance=[{"source_archive": "A.zip"}])
    with_archive_b = dict(base_record, source_provenance=[{"source_archive": "B.zip"}])

    assert trainer._logical_document_fingerprint(with_archive_a) == trainer._logical_document_fingerprint(with_archive_b)


def test_archive_member_naming_is_deterministic(tmp_path):
    archive_path = tmp_path / "downloads.zip"
    member = "nested/OFERTAS FIM DE SEMANA NOVA.pptx"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member, b"pptx")

    trainer = _trainer(tmp_path)
    first = trainer._extract_zip_pptx(archive_path, [])[0]
    second = trainer._extract_zip_pptx(archive_path, [])[0]
    expected_prefix = hashlib.sha256(member.encode("utf-8")).hexdigest()[:12]

    assert first == second
    assert first.name == f"{expected_prefix}__OFERTAS FIM DE SEMANA NOVA.pptx"
