import io
import zipfile
from pathlib import Path

from srstudio.images.product_priority import scan_product_priority


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _pptx_bytes(slides, *, extra=b"") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index, texts in enumerate(slides, start=1):
            shapes = []
            for shape_index, text in enumerate(texts, start=1):
                shapes.append(
                    f'<p:sp><p:nvSpPr/><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
                    f'<a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>'
                )
            xml = (
                f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree>'
                + "".join(shapes)
                + '</p:spTree></p:cSld></p:sld>'
            )
            archive.writestr(f"ppt/slides/slide{index}.xml", xml)
        if extra:
            archive.writestr("docProps/custom.bin", extra)
    return buffer.getvalue()


def test_priority_counts_occurrences_and_independent_sources(tmp_path):
    first = tmp_path / "first.pptx"
    second = tmp_path / "second.pptx"
    first.write_bytes(
        _pptx_bytes([
            ["ARROZ PATOSUL 5KG", "DETERGENTE YPE 500ML"],
            ["ARROZ PATOSUL 5KG"],
        ])
    )
    second.write_bytes(_pptx_bytes([["ARROZ PATOSUL 5KG", "MONSTER 473ML"]]))

    report = scan_product_priority([first, second], catalog_names=["ARROZ PATOSUL 5KG"])
    rows = {row.normalized_name: row for row in report.rows}

    assert rows["ARROZ PATOSUL 5KG"].occurrence_count == 3
    assert rows["ARROZ PATOSUL 5KG"].source_count == 2
    assert rows["ARROZ PATOSUL 5KG"].catalog_present is True
    assert rows["DETERGENTE YPE 500ML"].occurrence_count == 1
    assert report.product_occurrences == 5


def test_semantically_equal_export_copy_does_not_inflate_priority(tmp_path):
    first = tmp_path / "one.pptx"
    export_copy = tmp_path / "two.pptx"
    first.write_bytes(_pptx_bytes([["CAFE VASCONCELOS 500G"]], extra=b"package-a"))
    export_copy.write_bytes(_pptx_bytes([["CAFE VASCONCELOS 500G"]], extra=b"package-b"))

    report = scan_product_priority([first, export_copy])
    row = report.rows[0]

    assert report.exact_documents == 2
    assert report.logical_documents == 1
    assert row.occurrence_count == 1
    assert row.source_count == 1


def test_zip_members_are_scanned_without_destructive_extraction(tmp_path):
    archive_path = tmp_path / "Downloads.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("campanhas/TERCA VERDE.pptx", _pptx_bytes([["BANANA NANICA KG", "TOMATE PERA KG"]]))
        archive.writestr("readme.txt", "ignore")

    report = scan_product_priority([archive_path])
    names = {row.normalized_name for row in report.rows}

    assert report.files_seen == 1
    assert names == {"BANANA NANICA KG", "TOMATE PERA KG"}
    assert list(tmp_path.glob("**/TERCA VERDE.pptx")) == []


def test_missing_or_unsupported_source_is_warning_not_exception(tmp_path):
    report = scan_product_priority([tmp_path / "missing.zip", tmp_path / "note.txt"])
    assert report.rows == ()
    assert report.warnings
