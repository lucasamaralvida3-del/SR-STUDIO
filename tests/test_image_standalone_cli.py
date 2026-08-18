import json
import sqlite3
from pathlib import Path

from PIL import Image

from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_cli import (
    catalog_names_from_sqlite,
    discover_images,
    merge_sources,
    report_payload,
    run_incremental_standalone,
    write_report,
)
from srstudio.images.standalone_training import StandaloneImageSource, StandaloneTrainingReport


def _image(path: Path, color="white") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 180), color).save(path)
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


def test_catalog_names_supports_real_atacado_ultimo_nome_schema(tmp_path):
    database = tmp_path / "atacado_historico.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE products(codigo TEXT, ultimo_nome TEXT, ignorado INTEGER)")
        connection.executemany(
            "INSERT INTO products(codigo, ultimo_nome, ignorado) VALUES(?, ?, ?)",
            [
                ("32438", "ACHOCOLATADO EM PO TODDY 750G", 0),
                ("111836", "ACUCAR DELTA 5KG", 0),
            ],
        )

    names = catalog_names_from_sqlite(database)
    assert names == ["ACHOCOLATADO EM PO TODDY 750G", "ACUCAR DELTA 5KG"]


def test_catalog_names_supports_real_produtos_table_read_only(tmp_path):
    database = tmp_path / "atacado_historico.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE produtos(codigo TEXT, ultimo_nome TEXT, unidade_preferida TEXT, ignorado INTEGER)"
        )
        connection.executemany(
            "INSERT INTO produtos(codigo, ultimo_nome, unidade_preferida, ignorado) VALUES(?, ?, ?, ?)",
            [
                ("32438", "ACHOCOLATADO EM PO TODDY 750G", "UN", 0),
                ("111836", "ACUCAR DELTA 5KG", "UN", 0),
            ],
        )
        connection.execute("CREATE TABLE itens_relatorio(id INTEGER PRIMARY KEY)")

    before = database.read_bytes()
    names = catalog_names_from_sqlite(database)
    after = database.read_bytes()

    assert names == ["ACHOCOLATADO EM PO TODDY 750G", "ACUCAR DELTA 5KG"]
    assert after == before


def test_catalog_names_supports_name_only_schema(tmp_path):
    database = tmp_path / "products.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE products(name TEXT)")
        connection.execute("INSERT INTO products(name) VALUES('MONSTER 473ML')")
    assert catalog_names_from_sqlite(database) == ["MONSTER 473ML"]


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


def test_incremental_standalone_skips_unchanged_input(tmp_path):
    image = _image(tmp_path / "MONSTER 473ML.png")
    source = StandaloneImageSource(str(image))
    library = SafeImageLibrary(tmp_path / "bank")
    state = tmp_path / "standalone_state.json"

    first, first_skipped, total = run_incremental_standalone(
        library, [source], ["MONSTER 473ML"], state_path=state
    )
    second, second_skipped, second_total = run_incremental_standalone(
        library, [source], ["MONSTER 473ML"], state_path=state
    )

    assert first.discovered == 1
    assert first_skipped == 0
    assert total == 1
    assert second.discovered == 0
    assert second_skipped == 1
    assert second_total == 1


def test_incremental_standalone_reprocesses_only_changed_file(tmp_path):
    first_path = _image(tmp_path / "MONSTER 473ML.png", "white")
    second_path = _image(tmp_path / "DETERGENTE YPE 500ML.png", "gray")
    sources = [StandaloneImageSource(str(first_path)), StandaloneImageSource(str(second_path))]
    catalog = ["MONSTER 473ML", "DETERGENTE YPE 500ML"]
    library = SafeImageLibrary(tmp_path / "bank")
    state = tmp_path / "state.json"

    run_incremental_standalone(library, sources, catalog, state_path=state)
    _image(first_path, "black")
    report, skipped, total = run_incremental_standalone(library, sources, catalog, state_path=state)

    assert total == 2
    assert skipped == 1
    assert report.discovered == 1
    assert Path(report.matches[0].path).name == "MONSTER 473ML.png"


def test_incremental_standalone_reprocesses_when_catalog_changes(tmp_path):
    image = _image(tmp_path / "MONSTER 473ML.png")
    source = StandaloneImageSource(str(image))
    library = SafeImageLibrary(tmp_path / "bank")
    state = tmp_path / "state.json"

    first, _, _ = run_incremental_standalone(library, [source], [], state_path=state)
    second, skipped, _ = run_incremental_standalone(
        library, [source], ["MONSTER 473ML"], state_path=state
    )

    assert first.unknown == 1
    assert skipped == 0
    assert second.review == 1


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
    data = report_payload(
        report,
        discovery_warnings=["discovery warning"],
        skipped=2,
        discovered_total=5,
    )

    target = write_report(tmp_path / "standalone.json", data)
    loaded = json.loads(target.read_text(encoding="utf-8"))

    assert loaded["metrics"] == {
        "discovered": 5,
        "processed": 3,
        "skipped": 2,
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
