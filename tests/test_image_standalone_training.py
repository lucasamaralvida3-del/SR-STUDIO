import json
from pathlib import Path

from PIL import Image

from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_training import (
    StandaloneImageSource,
    StandaloneProductImageTrainer,
    load_manifest,
)


def _image(path: Path, color=(30, 90, 180)) -> Path:
    Image.new("RGB", (320, 480), color).save(path)
    return path


def test_verified_manifest_mapping_auto_accepts_with_standalone_provenance(tmp_path):
    source = _image(tmp_path / "image23.png")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(library, ["CAFE VASCONCELOS 500G"])

    report = trainer.train(
        [
            StandaloneImageSource(
                str(source),
                product_name="CAFÉ VASCONCELOS 500G",
                verified=True,
                provenance={"library_file_id": "file-123"},
            )
        ]
    )

    assert report.accepted == 1
    assert report.imported == 1
    asset = library.find_for_product("CAFE VASCONCELOS 500G")[0]
    assert asset.review_status == "accepted"
    assert asset.source == "standalone-library"
    assert asset.metadata["verified_mapping"] is True
    assert asset.metadata["provenance"][0]["source_kind"] == "standalone-library"
    assert asset.metadata["provenance"][0]["library_file_id"] == "file-123"


def test_exact_catalog_filename_can_auto_accept_without_filename_id_dependency(tmp_path):
    source = _image(tmp_path / "MONSTER 473ML.png")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(library, ["MONSTER 473ML"])

    report = trainer.train([StandaloneImageSource(str(source))])

    assert report.accepted == 1
    assert report.matches[0].reason == "exact-catalog-name"
    assert library.find_for_product("MONSTER 473ML")[0].review_status == "accepted"


def test_different_gramature_does_not_match_catalog_variant(tmp_path):
    source = _image(tmp_path / "TODDY 370G.png")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(library, ["TODDY 750G"])

    report = trainer.train([StandaloneImageSource(str(source))])

    assert report.unknown == 1
    assert report.imported == 0
    assert library.all() == []


def test_ambiguous_catalog_match_stays_pending(tmp_path):
    source = _image(tmp_path / "LEITE TRIANGULO 1L.png")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(
        library,
        [
            "LEITE TRIANGULO 1L INTEGRAL",
            "LEITE TRIANGULO 1L DESNATADO",
        ],
    )

    report = trainer.train([StandaloneImageSource(str(source))])

    assert report.review == 1
    assert report.accepted == 0
    assert report.matches[0].status == "review"
    asset = library.find_for_product(report.matches[0].product_name)[0]
    assert asset.review_status == "pending"


def test_existing_canva_duplicate_keeps_original_scalar_source_and_adds_provenance(tmp_path):
    source = _image(tmp_path / "CAFE VASCONCELOS 500G.png")
    library = SafeImageLibrary(tmp_path / "bank")
    original = library.learn_product_image(
        source,
        "CAFE VASCONCELOS 500G",
        confidence=.95,
        source_file="encarte.pptx",
        metadata={"provenance": [{"source_kind": "canva", "source_file": "encarte.pptx"}]},
    )
    assert original.source == "canva"

    trainer = StandaloneProductImageTrainer(library, ["CAFE VASCONCELOS 500G"])
    report = trainer.train([StandaloneImageSource(str(source), provenance={"library_file_id": "standalone-1"})])

    assert report.accepted == 1
    asset = library.find_for_product("CAFE VASCONCELOS 500G")[0]
    assert asset.source == "canva"
    kinds = {row["source_kind"] for row in asset.metadata["provenance"]}
    assert kinds == {"canva", "standalone-library"}


def test_manifest_loader_preserves_explicit_verification_and_provenance(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "images": [
                    {
                        "path": "produto.png",
                        "label": "produto",
                        "product_name": "DETERGENTE YPE 500ML",
                        "verified": True,
                        "provenance": {"source": "library"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = load_manifest(manifest)

    assert len(rows) == 1
    assert rows[0].verified is True
    assert rows[0].product_name == "DETERGENTE YPE 500ML"
    assert rows[0].provenance == {"source": "library"}


def test_missing_standalone_file_is_warning_not_destructive(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(library, ["MONSTER 473ML"])

    report = trainer.train([StandaloneImageSource(str(tmp_path / "missing.png"), label="MONSTER 473ML")])

    assert report.unknown == 1
    assert report.imported == 0
    assert report.warnings
    assert library.all() == []
