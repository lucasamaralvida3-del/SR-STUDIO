import json
import sqlite3
from pathlib import Path

from PIL import Image

from srstudio.images.standalone_cli import (
    catalog_names_from_sqlite,
    discover_images,
    merge_sources,
    report_payload,
    write_report,
)
from srstudio.images.standalone_training import StandaloneImageSource, StandaloneTrainingReport


def _image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 180), "white").save(path)
    return path


def test_discover_images_recurses_and_ignores_non_image_files(tmp_path):
    _image(tmp_path / "MONSTER 473ML.png")
    _image(tmp_path / "sub" / "1000255371.jpg")
    (tmp_path / "notes.txt").write_text("not an image", encoding="utf-8")

    rows, warnings = discover_images([tmp_path])

    assert warnings == []
    assert {Path(row.path).name for row in rows} == {"MONSTER 473ML.png", "1000255371.jpg"}
    assert all(row.product_name == "" for row in rows)
    assert all(row.verified is False for row in rows)


def test_discover_images_deduplicates_same_path_from_overlapping_sources(tmp_path):
    image = _image(tmp_path / "DETERGENTE YPE 500ML.png")

    rows, warnings = discover_images([tmp_path, image])

    assert warnings == []
    assert len(rows) == 1


def test_catalog_names_from_sqlite_is_read_only_and_prefers_display_name(tmp_path):
    database = tmp_path / "products.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE products(name TEXT, display_name TEXT)")
        connection.executemany(
            "INSERT INTO products(name, display_name) VALUES(?, ?)",
            [
                ("CAFE VASCONCELOS 500G", "Café Vasconcelos 500 G"),
                ("MONSTER 473ML", ""),
            ],
        )

    before = database.stat().st_size
    names = catalog_names_from_sqlite(database)
    after = database.stat().st_size

    assert names == ["Café Vasconcelos 500 G", "MONSTER 473ML"]
    assert after == before


def test_merge_sources_prefers_manifest_evidence_for_same_file(tmp_path):
    image = _image(tmp_path / "image23.png")
    discovered = [StandaloneImageSource(str(image))]
    manifest = [
        StandaloneImageSource(
            str(image),
            product_name="PAO DE QUEIJO CONGELADO SR 1KG",
            verified=True,
            provenance={"verified_by": "corpus"},
        )
    ]

    merged = merge_sources(discovered, manifest)

    assert len(merged) == 1
    assert merged[0].verified is True
    assert merged[0].product_name == "PAO DE QUEIJO CONGELADO SR 1KG"


def test_report_writer_is_atomic_json_contract(tmp_path):
    report = StandaloneTrainingReport(
        discovered=3,
        accepted=1,
        review=1,
        unknown=1,
        imported=2,
        matches=(),
        warnings=("trainer warning",),
    )
    payload = report_payload(report, discovery_warnings=["discovery warning"])

    target = write_report(tmp_path / "standalone.json", payload)
    loaded = json.loads(target.read_text(encoding="utf-8"))

    assert loaded["metrics"] == {
        "discovered": 3,
        "accepted": 1,
        "review": 1,
        "unknown": 1,
        "imported": 2,
    }
    assert loaded["warnings"] == ["discovery warning", "trainer warning"]


def test_missing_source_is_warning_not_exception(tmp_path):
    rows, warnings = discover_images([tmp_path / "missing"])
    assert rows == []
    assert warnings
