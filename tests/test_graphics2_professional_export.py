from __future__ import annotations

from pathlib import Path

from srstudio.graphics2 import GraphicsDocument, GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.qt_renderer import render_pdf, render_png


def _editable_document() -> GraphicsDocument:
    session = GraphicsSession(GraphicsDocument(name="Encarte exportável"))
    title = session.add_text("OFERTAS SR", x=80, y=70, width=520, height=90, name="Título")
    session.select(title.id)
    session.move_selected(10, 5)
    session.add_page(duplicate_active=True)
    session.add_text("PÁGINA 2", x=100, y=180, width=420, height=80, name="Página 2")
    return session.document


def test_professional_scene_survives_save_reopen_and_exports_png_pdf(tmp_path: Path):
    document = _editable_document()
    scene_path = save_package(document, tmp_path / "encarte.srscene", embed_local_assets=False)
    restored = load_package(scene_path)

    assert len(restored.pages) == 2
    assert restored.active_page_id == restored.pages[1].id

    png = render_png(restored, tmp_path / "preview.png", page_index=1, dpi=96)
    pdf = render_pdf(restored, tmp_path / "encarte.pdf", dpi=144)

    assert png.ok is True
    assert png.pages == 1
    assert png.width > 0 and png.height > 0
    assert png.output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    assert pdf.ok is True
    assert pdf.pages == 2
    assert pdf.output.read_bytes().startswith(b"%PDF")
