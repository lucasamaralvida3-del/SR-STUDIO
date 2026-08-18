from __future__ import annotations

import os
from pathlib import Path

import pytest

import srstudio
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.import_bridge import GraphicsImportService
from srstudio.graphics2.model import NodeKind
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity
from srstudio.graphics2.qt_renderer import render_pdf, render_png


PPTX_NAMES = (
    "ATACADO.pptx",
    "CARTAZ_VENDA.pptx",
    "CLUBE_EXCLUSIVO.pptx",
    "SEGUNDA_DA_LIMPEZA.pptx",
    "SEGUNDA_DA_LIMPEZA_2.pptx",
    "SEGUNDA_DA_LIMPEZA_3.pptx",
    "SEGUNDA_DA_LIMPEZA_4.pptx",
)


def _pptx_root() -> Path:
    return Path(srstudio.__file__).resolve().parent / "assets" / "poster_templates" / "legacy" / "models"


def _pptx_path(name: str) -> Path:
    path = _pptx_root() / name
    assert path.is_file(), f"Template PPTX de QA ausente: {path}"
    return path


def _node_count(document) -> int:
    return sum(len(page.nodes) for page in document.pages)


def _editable_node(router: GraphicsCommandRouter, kind: NodeKind):
    for page in router.session.document.pages:
        selected_page = router.dispatch({"name": "select_page", "page_id": page.id})
        assert selected_page.ok
        for node in page.nodes.values():
            if node.kind is kind and not router.session.effective_locked(node.id):
                return page, node
    return None, None


def _import_editable_pptx() -> tuple[Path, GraphicsCommandRouter]:
    service = GraphicsImportService()
    diagnostics: list[str] = []
    for name in PPTX_NAMES:
        path = _pptx_path(name)
        result = service.import_file(path)
        document = result.document
        assert_document_integrity(document)
        router = GraphicsCommandRouter(GraphicsSession(document))
        _text_page, text_node = _editable_node(router, NodeKind.TEXT)
        _image_page, image_node = _editable_node(router, NodeKind.IMAGE)
        diagnostics.append(
            f"{name}: pages={len(document.pages)} nodes={_node_count(document)} "
            f"editable_text={bool(text_node)} editable_image={bool(image_node)}"
        )
        if text_node is not None and image_node is not None:
            return path, router
    pytest.fail(
        "Nenhum PPTX real do corpus produziu texto e imagem simultaneamente editáveis no G2. "
        + " | ".join(diagnostics)
    )


@pytest.mark.parametrize("name", ("ATACADO.pptx", "CARTAZ_VENDA.pptx", "SEGUNDA_DA_LIMPEZA.pptx"))
def test_real_pptx_imports_to_valid_sr_scene_without_empty_pages(name):
    pytest.importorskip("pptx")
    result = GraphicsImportService().import_file(_pptx_path(name))
    document = result.document

    assert document.pages, f"{name} importou sem páginas."
    assert_document_integrity(document)
    assert _node_count(document) > 0, f"{name} importou sem elementos."
    assert all(page.width > 0 and page.height > 0 for page in document.pages)
    assert document.metadata.get("graphics2_import_bridge") == 2
    assert document.metadata.get("import_summary", {}).get("source")
    assert document.metadata.get("pptx_structure")
    fingerprint = str(document.metadata.get("import_fingerprint_sha256") or "")
    assert len(fingerprint) == 64


def test_real_pptx_import_edit_save_reopen_and_export_png_pdf(tmp_path):
    pytest.importorskip("pptx")
    pytest.importorskip("PIL.Image")
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PIL import Image
    from PySide6.QtGui import QGuiApplication
    from pypdf import PdfReader

    _app = QGuiApplication.instance() or QGuiApplication([])
    source_pptx, router = _import_editable_pptx()
    original_page_ids = [page.id for page in router.session.document.pages]

    # Navegar todas as páginas importadas pelo mesmo Command Router usado pela UI.
    for page_id in original_page_ids:
        selected = router.dispatch({"name": "select_page", "page_id": page_id})
        assert selected.ok
        assert router.session.document.active_page_id == page_id

    text_page, text_node = _editable_node(router, NodeKind.TEXT)
    image_page, image_node = _editable_node(router, NodeKind.IMAGE)
    assert text_page is not None and text_node is not None
    assert image_page is not None and image_node is not None

    assert router.dispatch({"name": "select_page", "page_id": text_page.id}).ok
    edited_text = f"QA PPTX EDITADO — {source_pptx.stem}"
    edited = router.dispatch({"name": "edit_text", "node_id": text_node.id, "text": edited_text})
    assert edited.ok and edited.changed
    assert router.session.page.node(text_node.id).text == edited_text

    replacement_path = tmp_path / "qa-pptx-replacement.png"
    Image.new("RGB", (320, 240), (37, 149, 211)).save(replacement_path, format="PNG")
    assert router.dispatch({"name": "select_page", "page_id": image_page.id}).ok
    replaced = router.dispatch(
        {"name": "replace_image", "node_id": image_node.id, "source": replacement_path.as_uri()}
    )
    assert replaced.ok and replaced.changed
    replacement_asset_id = replaced.payload["asset_id"]
    assert router.session.page.node(image_node.id).asset_id == replacement_asset_id

    # Save -> close/reopen deve preservar estrutura, texto, imagem e paginação importada.
    project = tmp_path / "pptx-flow.srscene"
    save_package(router.session.document, project, embed_local_assets=True)
    reopened = load_package(project, extract_assets_to=tmp_path / "reopened-assets")
    assert_document_integrity(reopened)
    assert len(reopened.pages) == len(original_page_ids)
    assert [page.id for page in reopened.pages] == original_page_ids
    assert any(
        node.id == text_node.id and node.text == edited_text
        for page in reopened.pages
        for node in page.nodes.values()
    )
    reopened_image = next(
        node for page in reopened.pages for node in page.nodes.values() if node.id == image_node.id
    )
    assert reopened_image.asset_id == replacement_asset_id
    assert Path(reopened.assets[replacement_asset_id].source).is_file()

    png_path = tmp_path / "pptx-flow.png"
    png_report = render_png(reopened, png_path, page_index=0, dpi=96, target_width=1080)
    assert png_report.output == png_path
    assert png_path.is_file() and png_path.stat().st_size > 100
    with Image.open(png_path) as png:
        assert png.format == "PNG"
        assert png.width == 1080
        assert png.height > 0

    pdf_path = tmp_path / "pptx-flow.pdf"
    pdf_report = render_pdf(reopened, pdf_path, dpi=96)
    assert pdf_report.output == pdf_path
    assert pdf_report.pages == len(reopened.pages)
    assert pdf_path.is_file() and pdf_path.stat().st_size > 100
    assert pdf_path.read_bytes().startswith(b"%PDF")
    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) == len(reopened.pages)
