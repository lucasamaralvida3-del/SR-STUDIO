from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pypdfium2 as pdfium
from PySide6.QtGui import QImage

from srstudio.graphics2.export_output import ExportValidationError, export_jpeg, export_pdf, export_png
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform


def _solid_document(colors: list[str], *, width: float = 96, height: float = 96) -> GraphicsDocument:
    document = GraphicsDocument(name="Round-trip")
    first = document.pages[0]
    first.width = width
    first.height = height
    first.background = colors[0]
    document.pages = [first]
    for index, color in enumerate(colors[1:], start=2):
        page = document.add_page()
        page.name = f"Página {index}"
        page.width = width
        page.height = height
        page.background = color
    document.active_page_id = document.pages[0].id
    return document


def _assert_rgb_close(actual, expected: tuple[int, int, int], *, tolerance: int = 5) -> None:
    rgb = tuple(int(value) for value in actual[:3])
    assert all(abs(value - target) <= tolerance for value, target in zip(rgb, expected)), (rgb, expected)


def test_png_roundtrip_preserves_opaque_page_background(tmp_path):
    document = _solid_document(["#123456"], width=320, height=400)
    report = export_png(document, tmp_path / "opaque.png", target_width=320, dpi=96)

    image = QImage(str(report.output))
    pixel = image.pixelColor(160, 200)
    assert pixel.alpha() == 255
    assert (pixel.red(), pixel.green(), pixel.blue()) == (0x12, 0x34, 0x56)


def test_pdf_roundtrip_preserves_same_size_page_order_and_background(tmp_path):
    document = _solid_document(["#FF0000", "#00FF00", "#0000FF"], width=96, height=96)
    report = export_pdf(document, tmp_path / "ordered.pdf", dpi=144, page_indices=[2, 0, 1])

    pdf = pdfium.PdfDocument(str(report.output))
    try:
        assert len(pdf) == 3
        expected = [(0, 0, 255), (255, 0, 0), (0, 255, 0)]
        for index, expected_rgb in enumerate(expected):
            page = pdf[index]
            bitmap = page.render(scale=1.0)
            try:
                image = bitmap.to_pil().convert("RGB")
                center = image.getpixel((image.width // 2, image.height // 2))
                _assert_rgb_close(center, expected_rgb)
            finally:
                bitmap.close()
                page.close()
    finally:
        pdf.close()


def test_pdf_single_selected_page_is_exact_requested_page(tmp_path):
    document = _solid_document(["#AA0000", "#00AA00", "#0000AA"], width=96, height=96)
    report = export_pdf(document, tmp_path / "page-2.pdf", dpi=144, page_indices=[1])

    pdf = pdfium.PdfDocument(str(report.output))
    try:
        assert len(pdf) == 1
        page = pdf[0]
        bitmap = page.render(scale=1.0)
        try:
            image = bitmap.to_pil().convert("RGB")
            center = image.getpixel((image.width // 2, image.height // 2))
            _assert_rgb_close(center, (0, 170, 0))
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()


def test_jpeg_quality_parameter_changes_encoded_output(tmp_path):
    document = _solid_document(["#FFFFFF"], width=320, height=400)
    page = document.pages[0]
    for index in range(20):
        page.add_node(
            GraphicsNode(
                kind=NodeKind.RECT,
                transform=Transform(
                    x=float((index % 5) * 64),
                    y=float((index // 5) * 100),
                    width=64,
                    height=100,
                ),
                style={"fill": f"#{(index * 37) % 256:02X}{(index * 73) % 256:02X}{(index * 109) % 256:02X}"},
            )
        )

    low = export_jpeg(document, tmp_path / "low.jpg", target_width=640, quality=20)
    high = export_jpeg(document, tmp_path / "high.jpg", target_width=640, quality=100)

    assert low.output.read_bytes() != high.output.read_bytes()
    assert high.output.stat().st_size > low.output.stat().st_size


def test_missing_raster_asset_fails_without_publishing_file(tmp_path):
    document = _solid_document(["#FFFFFF"], width=100, height=100)
    missing = (tmp_path / "missing-product.png").resolve()
    document.pages[0].add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            transform=Transform(x=0, y=0, width=100, height=100),
            metadata={"source_url": str(missing)},
        )
    )
    target = tmp_path / "should-not-exist.png"

    with pytest.raises(ExportValidationError, match="recurso obrigatório"):
        export_png(document, target, target_width=100, strict_assets=True)
    assert not target.exists()


def test_raster_renderer_failure_preserves_previous_destination(monkeypatch, tmp_path):
    from srstudio.graphics2 import export_output

    document = _solid_document(["#FFFFFF"], width=100, height=100)
    target = tmp_path / "existing.png"
    target.write_bytes(b"previous-good")

    def fail_render(*_args, **_kwargs):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(export_output._renderer, "_render_page", fail_render)
    with pytest.raises(RuntimeError, match="renderer exploded"):
        export_png(document, target, target_width=100)
    assert target.read_bytes() == b"previous-good"
