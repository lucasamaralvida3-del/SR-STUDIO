from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from pypdf import PdfReader

from srstudio.graphics2.export_output import (
    ExportValidationError,
    export_jpeg,
    export_pdf,
    export_png,
    export_raster_batch,
)
from srstudio.graphics2.model import CoordinateUnit, GraphicsDocument, GraphicsPage


def _page(*, name: str, width: float, height: float, unit: CoordinateUnit, background: str) -> GraphicsPage:
    return GraphicsPage(name=name, width=width, height=height, unit=unit, background=background)


def _document_with_pages(count: int, *, width: float = 1080, height: float = 1350) -> GraphicsDocument:
    document = GraphicsDocument(name="Encarte SR")
    document.pages = []
    for index in range(count):
        document.pages.append(
            _page(
                name=f"Página {index + 1}",
                width=width,
                height=height,
                unit=CoordinateUnit.PIXEL,
                background=f"#{(index * 37) % 255:02X}3366",
            )
        )
    document.active_page_id = document.pages[0].id if document.pages else ""
    return document


def _pdf_page_size_points(path, page_index: int) -> tuple[float, float]:
    page = PdfReader(str(path)).pages[page_index]
    return float(page.mediabox.width), float(page.mediabox.height)


def test_png_exports_exact_social_dimensions_with_real_alpha_and_dpi(tmp_path):
    document = _document_with_pages(1)
    document.pages[0].background = "#123456"

    report = export_png(
        document,
        tmp_path / "nested" / "instagram.anything",
        target_width=1080,
        target_height=1350,
        dpi=300,
        transparent=True,
    )

    assert report.ok
    assert report.output.name == "instagram.png"
    assert (report.width, report.height) == (1080, 1350)
    image = QImage(str(report.output))
    assert image.hasAlphaChannel()
    assert image.pixelColor(0, 0).alpha() == 0
    expected_dpm = round(300 / 0.0254)
    assert image.dotsPerMeterX() == pytest.approx(expected_dpm, abs=1)
    assert image.dotsPerMeterY() == pytest.approx(expected_dpm, abs=1)


def test_png_dpi_only_a4_300_matches_physical_resolution(tmp_path):
    document = GraphicsDocument(name="A4 PNG")
    document.pages = [
        _page(
            name="A4",
            width=210,
            height=297,
            unit=CoordinateUnit.MILLIMETER,
            background="#FFFFFF",
        )
    ]
    document.active_page_id = document.pages[0].id

    report = export_png(document, tmp_path / "a4-300.png", dpi=300)

    assert report.ok
    assert (report.width, report.height) == (2480, 3508)
    image = QImage(str(report.output))
    expected_dpm = round(300 / 0.0254)
    assert image.dotsPerMeterX() == pytest.approx(expected_dpm, abs=1)
    assert image.dotsPerMeterY() == pytest.approx(expected_dpm, abs=1)


def test_public_renderer_host_path_uses_production_output_guard(tmp_path):
    from srstudio.graphics2 import qt_renderer

    assert qt_renderer._sr_production_output_guard_installed is True
    assert hasattr(qt_renderer, "render_jpeg")
    assert hasattr(qt_renderer, "render_raster_batch")

    document = _document_with_pages(1, width=96, height=120)
    report = qt_renderer.render_png(document, tmp_path / "host-path.png", dpi=96)
    assert report.ok
    assert (report.width, report.height) == (96, 120)


def test_png_rejects_dimension_pair_that_would_distort_page(tmp_path):
    document = _document_with_pages(1)
    with pytest.raises(ValueError, match="proporção"):
        export_png(document, tmp_path / "bad.png", target_width=1080, target_height=1080)


def test_png_accepts_custom_height_without_distortion(tmp_path):
    document = _document_with_pages(1, width=1080, height=1350)
    report = export_png(document, tmp_path / "custom-height.png", target_height=2700)
    assert (report.width, report.height) == (2160, 2700)


def test_raster_rejects_unsafe_giant_allocation_before_qimage(tmp_path):
    document = _document_with_pages(1, width=100, height=100)
    with pytest.raises(ValueError, match="memória segura"):
        export_png(document, tmp_path / "giant.png", target_width=20_000, target_height=20_000)


def test_jpeg_exports_exact_dimensions_and_composites_opaque_background(tmp_path):
    document = _document_with_pages(1, width=400, height=500)
    document.pages[0].background = "#00FF00"

    report = export_jpeg(
        document,
        tmp_path / "share.png",
        target_width=800,
        quality=88,
        background="#336699",
    )

    assert report.ok
    assert report.output.suffix == ".jpg"
    assert (report.width, report.height) == (800, 1000)
    image = QImage(str(report.output))
    pixel = image.pixelColor(20, 20)
    assert pixel.alpha() == 255
    assert pixel.red() == pytest.approx(0x33, abs=8)
    assert pixel.green() == pytest.approx(0x66, abs=8)
    assert pixel.blue() == pytest.approx(0x99, abs=8)


def test_jpeg_accepts_jpeg_extension_and_validates_quality(tmp_path):
    document = _document_with_pages(1, width=100, height=100)
    report = export_jpeg(document, tmp_path / "photo.jpeg", target_width=100, quality=100)
    assert report.output.suffix == ".jpeg"
    with pytest.raises(ValueError, match="1 e 100"):
        export_jpeg(document, tmp_path / "bad.jpg", quality=0)


def test_jpeg_dpi_metadata_is_written_when_supported_by_qt_plugin(tmp_path):
    document = _document_with_pages(1, width=96, height=96)
    report = export_jpeg(document, tmp_path / "dpi.jpg", dpi=150)
    image = QImage(str(report.output))
    expected_dpm = round(150 / 0.0254)
    assert image.dotsPerMeterX() == pytest.approx(expected_dpm, abs=120)
    assert image.dotsPerMeterY() == pytest.approx(expected_dpm, abs=120)


def test_pdf_single_page_preserves_a4_physical_size(tmp_path):
    document = GraphicsDocument(name="A4")
    document.pages = [_page(name="A4", width=210, height=297, unit=CoordinateUnit.MILLIMETER, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id

    report = export_pdf(document, tmp_path / "print", dpi=600)

    assert report.ok
    assert report.pages == 1
    assert report.output.suffix == ".pdf"
    width_pt, height_pt = _pdf_page_size_points(report.output, 0)
    assert width_pt == pytest.approx(210 * 72 / 25.4, abs=0.6)
    assert height_pt == pytest.approx(297 * 72 / 25.4, abs=0.6)


def test_pdf_multipage_preserves_requested_order_and_each_page_size(tmp_path):
    document = GraphicsDocument(name="Mixed")
    document.pages = [
        _page(name="A4 portrait", width=210, height=297, unit=CoordinateUnit.MILLIMETER, background="#FF0000"),
        _page(name="A4 landscape", width=297, height=210, unit=CoordinateUnit.MILLIMETER, background="#00FF00"),
        _page(name="Square", width=100, height=100, unit=CoordinateUnit.MILLIMETER, background="#0000FF"),
    ]
    document.active_page_id = document.pages[0].id

    report = export_pdf(document, tmp_path / "mixed.pdf", page_indices=[2, 0, 1], dpi=300)
    reader = PdfReader(str(report.output))

    assert report.pages == 3
    assert len(reader.pages) == 3
    sizes = [(float(page.mediabox.width), float(page.mediabox.height)) for page in reader.pages]
    assert sizes[0][0] == pytest.approx(100 * 72 / 25.4, abs=0.6)
    assert sizes[0][1] == pytest.approx(100 * 72 / 25.4, abs=0.6)
    assert sizes[1][0] == pytest.approx(210 * 72 / 25.4, abs=0.6)
    assert sizes[1][1] == pytest.approx(297 * 72 / 25.4, abs=0.6)
    assert sizes[2][0] == pytest.approx(297 * 72 / 25.4, abs=0.6)
    assert sizes[2][1] == pytest.approx(210 * 72 / 25.4, abs=0.6)


def test_pdf_ten_page_smoke_cannot_silently_lose_pages(tmp_path):
    document = _document_with_pages(10, width=96, height=120)
    report = export_pdf(document, tmp_path / "ten-pages.pdf", dpi=144)
    reader = PdfReader(str(report.output))
    assert report.pages == 10
    assert len(reader.pages) == 10


def test_pdf_rejects_duplicate_missing_or_empty_page_selection(tmp_path):
    document = _document_with_pages(3, width=100, height=100)
    with pytest.raises(ValueError, match="duplicadas"):
        export_pdf(document, tmp_path / "duplicate.pdf", page_indices=[0, 0])
    with pytest.raises(IndexError, match="Página inexistente"):
        export_pdf(document, tmp_path / "missing.pdf", page_indices=[3])
    with pytest.raises(ValueError, match="Nenhuma página"):
        export_pdf(document, tmp_path / "empty.pdf", page_indices=[])


def test_project_without_pages_fails_clearly(tmp_path):
    document = GraphicsDocument(name="Empty")
    document.pages = []
    document.active_page_id = ""
    with pytest.raises(ValueError, match="Projeto sem páginas"):
        export_png(document, tmp_path / "empty.png")
    with pytest.raises(ValueError, match="Projeto sem páginas"):
        export_pdf(document, tmp_path / "empty.pdf")


def test_output_parent_that_is_a_file_fails_without_touching_project(tmp_path):
    document = _document_with_pages(1, width=100, height=100)
    before = document.to_dict()
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("block", encoding="utf-8")

    with pytest.raises(OSError):
        export_png(document, blocker / "page.png", target_width=100)
    assert document.to_dict() == before


def test_batch_exports_three_pages_in_source_order_with_predictable_names(tmp_path):
    document = _document_with_pages(3, width=100, height=125)
    progress: list[tuple[int, int, str]] = []

    report = export_raster_batch(
        document,
        tmp_path / "png-batch",
        raster_format="png",
        target_width=200,
        progress=lambda done, total, item: progress.append((done, total, item.output.name)),
    )

    assert report.ok
    assert [item.output.name for item in report.outputs] == [
        "Encarte_SR_p001.png",
        "Encarte_SR_p002.png",
        "Encarte_SR_p003.png",
    ]
    assert progress == [
        (1, 3, "Encarte_SR_p001.png"),
        (2, 3, "Encarte_SR_p002.png"),
        (3, 3, "Encarte_SR_p003.png"),
    ]


def test_batch_exports_ten_jpegs_without_duplicate_or_missing_names(tmp_path):
    document = _document_with_pages(10, width=80, height=100)
    report = export_raster_batch(
        document,
        tmp_path / "jpeg-batch",
        raster_format="jpeg",
        target_width=80,
        jpeg_quality=80,
    )
    names = [item.output.name for item in report.outputs]
    assert report.pages == 10
    assert len(set(names)) == 10
    assert names[0].endswith("p001.jpg")
    assert names[-1].endswith("p010.jpg")
    assert all(item.ok for item in report.outputs)


def test_batch_page_range_keeps_source_page_numbers_in_filenames(tmp_path):
    document = _document_with_pages(5, width=80, height=100)
    report = export_raster_batch(
        document,
        tmp_path,
        raster_format="png",
        page_indices=[3, 1],
        base_name="intervalo",
        target_width=80,
    )
    assert [item.output.name for item in report.outputs] == ["intervalo_p004.png", "intervalo_p002.png"]


def test_repeat_export_atomically_overwrites_existing_file(tmp_path):
    document = _document_with_pages(1, width=100, height=100)
    target = tmp_path / "repeat.png"
    target.write_bytes(b"old-file")

    first = export_png(document, target, target_width=100)
    first_bytes = target.read_bytes()
    second = export_png(document, target, target_width=200)

    assert first.ok and second.ok
    assert first_bytes.startswith(b"\x89PNG")
    assert target.read_bytes().startswith(b"\x89PNG")
    assert QImage(str(target)).width() == 200


def test_overwrite_false_preserves_existing_file(tmp_path):
    document = _document_with_pages(1, width=100, height=100)
    target = tmp_path / "protected.png"
    target.write_bytes(b"keep-me")
    with pytest.raises(FileExistsError):
        export_png(document, target, target_width=100, overwrite=False)
    assert target.read_bytes() == b"keep-me"


def test_invalid_windows_filename_is_rejected_cross_platform(tmp_path):
    document = _document_with_pages(1, width=100, height=100)
    with pytest.raises(ValueError, match="reservado"):
        export_png(document, tmp_path / "CON.png", target_width=100)
    with pytest.raises(ValueError, match="caractere inválido"):
        export_png(document, tmp_path / "bad?.png", target_width=100)


def test_large_project_smoke_exports_sequentially_and_leaves_scene_unchanged(tmp_path):
    document = _document_with_pages(25, width=32, height=40)
    before = document.to_dict()

    report = export_raster_batch(
        document,
        tmp_path / "large",
        raster_format="png",
        target_width=32,
    )

    assert report.ok
    assert report.pages == 25
    assert document.to_dict() == before


def test_pdf_failure_does_not_replace_existing_destination(monkeypatch, tmp_path):
    from srstudio.graphics2 import export_output

    document = _document_with_pages(2, width=100, height=100)
    target = tmp_path / "production.pdf"
    target.write_bytes(b"known-good")

    def fail_mid_export(_document, output, **_kwargs):
        output.write_bytes(b"%PDF-1.4\npartial")
        raise RuntimeError("renderer failed on page 2")

    monkeypatch.setattr(export_output._renderer, "render_pdf", fail_mid_export)

    with pytest.raises(RuntimeError, match="page 2"):
        export_pdf(document, target)
    assert target.read_bytes() == b"known-good"
    assert not list(tmp_path.glob(".*.tmp.pdf"))


def test_pdf_renderer_report_page_loss_blocks_publish(monkeypatch, tmp_path):
    from srstudio.graphics2 import export_output
    from srstudio.graphics2.qt_renderer import RenderReport

    document = _document_with_pages(2, width=100, height=100)
    target = tmp_path / "lost-page.pdf"
    target.write_bytes(b"previous-good")

    def claims_one_page(_document, output, **_kwargs):
        output.write_bytes(b"%PDF-1.4\n%%EOF")
        return RenderReport(output=output, format="pdf", pages=1)

    monkeypatch.setattr(export_output._renderer, "render_pdf", claims_one_page)
    with pytest.raises(ExportValidationError, match="PDF incompleto"):
        export_pdf(document, target)
    assert target.read_bytes() == b"previous-good"


def test_strict_asset_failure_never_publishes_partial_output(monkeypatch, tmp_path):
    from srstudio.graphics2 import export_output
    from srstudio.graphics2.qt_renderer import RenderReport, RenderWarning

    document = _document_with_pages(1, width=100, height=100)
    target = tmp_path / "strict.pdf"

    def missing_asset(_document, output, **_kwargs):
        output.write_bytes(b"%PDF-1.4\n%%EOF")
        return RenderReport(
            output=output,
            format="pdf",
            pages=1,
            warnings=[RenderWarning("IMAGE_NOT_LOCAL", "missing", document.pages[0].id, "node-1")],
        )

    monkeypatch.setattr(export_output._renderer, "render_pdf", missing_asset)

    with pytest.raises(ExportValidationError, match="recurso obrigatório"):
        export_pdf(document, target, strict_assets=True)
    assert not target.exists()
