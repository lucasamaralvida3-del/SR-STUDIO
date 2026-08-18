import sqlite3
from pathlib import Path

from PIL import Image

from srstudio.images.barcode_seed import (
    BarcodeCatalogEntry,
    BarcodeSeedResolver,
    discover_barcode_catalog,
    manifest_payload,
    normalize_barcode,
)


class FakeProvider:
    def __init__(self, mapping=None, *, available=True):
        self.mapping = mapping or {}
        self.is_available = available

    def available(self):
        return self.is_available

    def read(self, image_path):
        return list(self.mapping.get(Path(image_path).name, []))


def _image(path: Path):
    Image.new("RGB", (320, 480), "white").save(path)
    return path


def test_barcode_normalization_accepts_gtin_lengths_and_rejects_noise():
    assert normalize_barcode("789 1234 5678 90") == "7891234567890"
    assert normalize_barcode("EAN: 7891234567890") == "7891234567890"
    assert normalize_barcode("123") == ""
    assert normalize_barcode("1" * 15) == ""


def test_catalog_discovery_is_read_only_and_finds_ean_column(tmp_path):
    database = tmp_path / "products.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE products(name TEXT, ean TEXT)")
        connection.executemany(
            "INSERT INTO products(name, ean) VALUES(?, ?)",
            [
                ("MONSTER 473ML", "7891234567890"),
                ("DETERGENTE YPE 500ML", "7899999999999"),
            ],
        )

    before = database.stat().st_size
    catalog, warnings = discover_barcode_catalog(database)
    after = database.stat().st_size

    assert warnings == []
    assert after == before
    assert {(row.barcode, row.product_name) for row in catalog} == {
        ("7891234567890", "MONSTER 473ML"),
        ("7899999999999", "DETERGENTE YPE 500ML"),
    }


def test_missing_barcode_column_disables_feature_without_schema_mutation(tmp_path):
    database = tmp_path / "products.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE products(name TEXT)")
        connection.execute("INSERT INTO products(name) VALUES('MONSTER 473ML')")

    catalog, warnings = discover_barcode_catalog(database)

    assert catalog == []
    assert warnings
    with sqlite3.connect(database) as connection:
        assert [row[1] for row in connection.execute("PRAGMA table_info(products)")] == ["name"]


def test_exact_single_barcode_catalog_match_generates_verified_manifest(tmp_path):
    source = _image(tmp_path / "image23.png")
    provider = FakeProvider({source.name: ["7891234567890"]})
    resolver = BarcodeSeedResolver(
        provider,
        [BarcodeCatalogEntry("7891234567890", "MONSTER 473ML")],
    )

    report = resolver.resolve([source])
    manifest = manifest_payload(report)

    assert report.resolved == 1
    assert report.review == 0
    assert manifest["images"] == [
        {
            "path": str(source),
            "product_name": "MONSTER 473ML",
            "verified": True,
            "provenance": {
                "match_method": "exact-barcode-catalog-match",
                "barcode": "7891234567890",
            },
        }
    ]


def test_same_barcode_mapped_to_multiple_products_is_review_not_verified(tmp_path):
    source = _image(tmp_path / "ambiguous.png")
    provider = FakeProvider({source.name: ["7891234567890"]})
    resolver = BarcodeSeedResolver(
        provider,
        [
            BarcodeCatalogEntry("7891234567890", "PRODUTO A 500G"),
            BarcodeCatalogEntry("7891234567890", "PRODUTO B 500G"),
        ],
    )

    report = resolver.resolve([source])

    assert report.resolved == 0
    assert report.review == 1
    assert manifest_payload(report)["images"] == []


def test_multiple_detected_barcodes_are_review_even_if_one_matches(tmp_path):
    source = _image(tmp_path / "flyer.jpg")
    provider = FakeProvider({source.name: ["7891234567890", "7899999999999"]})
    resolver = BarcodeSeedResolver(
        provider,
        [
            BarcodeCatalogEntry("7891234567890", "MONSTER 473ML"),
            BarcodeCatalogEntry("7899999999999", "DETERGENTE YPE 500ML"),
        ],
    )

    report = resolver.resolve([source])

    assert report.resolved == 0
    assert report.review == 1
    assert manifest_payload(report)["images"] == []


def test_unavailable_provider_does_not_guess_from_filename(tmp_path):
    source = _image(tmp_path / "MONSTER 473ML.png")
    resolver = BarcodeSeedResolver(
        FakeProvider(available=False),
        [BarcodeCatalogEntry("7891234567890", "MONSTER 473ML")],
    )

    report = resolver.resolve([source])

    assert report.resolved == 0
    assert report.unknown == 1
    assert report.warnings
    assert manifest_payload(report)["images"] == []
