from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
from PySide6.QtGui import QImage
from pypdf import PdfReader

from srstudio.graphics2.export_output import export_pdf, export_png
from srstudio.graphics2.model import CoordinateUnit, GraphicsDocument, GraphicsPage


def _document(page: GraphicsPage) -> GraphicsDocument:
    document = GraphicsDocument(name="Print contract")
    document.pages = [page]
    document.active_page_id = page.id
    return document


def test_a4_landscape_png_at_300_dpi_has_expected_pixel_dimensions(tmp_path):
    document = _document(
        GraphicsPage(
            name="A4 landscape",
            width=297,
            height=210,
            unit=CoordinateUnit.MILLIMETER,
            background="#FFFFFF",
        )
    )

    report = export_png(document, tmp_path / "a4-landscape.png", dpi=300)

    assert (report.width, report.height) == (3508, 2480)
    image = QImage(str(report.output))
    assert (image.width(), image.height()) == (3508, 2480)


def test_point_units_respect_dpi_contract(tmp_path):
    document = _document(
        GraphicsPage(
            name="1 inch",
            width=72,
            height=72,
            unit=CoordinateUnit.POINT,
            background="#FFFFFF",
        )
    )

    report = export_png(document, tmp_path / "one-inch.png", dpi=300)
    assert (report.width, report.height) == (300, 300)


def test_pdf_dpi_does_not_change_a4_physical_page_size(tmp_path):
    page = GraphicsPage(
        name="A4",
        width=210,
        height=297,
        unit=CoordinateUnit.MILLIMETER,
        background="#FFFFFF",
    )
    low = export_pdf(_document(page), tmp_path / "a4-72.pdf", dpi=72)
    high = export_pdf(_document(page), tmp_path / "a4-600.pdf", dpi=600)

    low_box = PdfReader(str(low.output)).pages[0].mediabox
    high_box = PdfReader(str(high.output)).pages[0].mediabox
    assert float(low_box.width) == pytest.approx(float(high_box.width), abs=0.2)
    assert float(low_box.height) == pytest.approx(float(high_box.height), abs=0.2)
    assert float(high_box.width) == pytest.approx(210 * 72 / 25.4, abs=0.6)
    assert float(high_box.height) == pytest.approx(297 * 72 / 25.4, abs=0.6)


def test_pdf_background_reaches_page_edges_without_implicit_margin(tmp_path):
    document = _document(
        GraphicsPage(
            name="Edge fill",
            width=96,
            height=96,
            unit=CoordinateUnit.PIXEL,
            background="#C02040",
        )
    )
    report = export_pdf(document, tmp_path / "edges.pdf", dpi=144)

    pdf = pdfium.PdfDocument(str(report.output))
    try:
        page = pdf[0]
        bitmap = page.render(scale=2.0)
        try:
            image = bitmap.to_pil().convert("RGB")
            expected = (0xC0, 0x20, 0x40)
            probes = [
                (1, 1),
                (image.width - 2, 1),
                (1, image.height - 2),
                (image.width - 2, image.height - 2),
                (image.width // 2, image.height // 2),
            ]
            for point in probes:
                actual = image.getpixel(point)
                assert all(abs(value - target) <= 6 for value, target in zip(actual, expected)), (point, actual)
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()


def test_invalid_dpi_is_rejected_before_export(tmp_path):
    document = _document(GraphicsPage(width=100, height=100, background="#FFFFFF"))
    with pytest.raises(ValueError, match="DPI"):
        export_png(document, tmp_path / "zero.png", dpi=0)
    with pytest.raises(ValueError, match="2400"):
        export_png(document, tmp_path / "too-high.png", dpi=2401)


@pytest.mark.skipif(os.name != "nt", reason="Windows file locking contract")
def test_file_in_use_fails_cleanly_and_preserves_existing_output(tmp_path):
    document = _document(GraphicsPage(width=100, height=100, background="#FFFFFF"))
    target = tmp_path / "locked.png"
    target.write_bytes(b"previous")

    with target.open("rb"):
        with pytest.raises(OSError, match="Não foi possível publicar"):
            export_png(document, target, target_width=100)

    assert target.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".*.tmp.png"))
