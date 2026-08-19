from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsDocument, GraphicsPage, GraphicsSession
from srstudio.graphics2 import import_ui_runtime


def test_project_actions_exposes_visible_pptx_canva_picker():
    qml = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "srstudio"
        / "graphics2"
        / "qml"
        / "ProjectActions.qml"
    ).read_text(encoding="utf-8")

    assert 'text: "Importar PPTX / Canva"' in qml
    assert 'ToolTip.text: "Importe um PowerPoint ou um projeto exportado do Canva em .pptx"' in qml
    assert 'id: importPptxDialog' in qml
    assert 'fileMode: FileDialog.OpenFile' in qml
    assert 'nameFilters: ["PowerPoint (*.pptx)"]' in qml
    assert '"name": "import_pptx"' in qml
    assert 'panel.importingPptx = true' in qml
    assert 'running: sceneBridge.busy || panel.importingPptx' in qml
    assert 'id: importErrorDialog' in qml
    assert 'text: "Não foi possível importar este arquivo PPTX."' in qml


def test_import_command_reuses_existing_graphics_import_service_and_opens_first_page(tmp_path, monkeypatch):
    source = tmp_path / "OFERTAS QUINTA FILÉ NOVO(1).pptx"
    source.write_bytes(b"pptx-marker")

    before = GraphicsDocument(name="Antes")
    session = GraphicsSession(before)
    router = GraphicsCommandRouter(session)

    imported = GraphicsDocument(name="Importado")
    first_id = imported.pages[0].id
    imported.pages.append(GraphicsPage(name="Página 2"))
    imported.pages.append(GraphicsPage(name="Página 3"))
    imported.active_page_id = imported.pages[2].id

    calls: list[tuple[Path, str]] = []

    class FakeImportService:
        def import_file(self, path, *, project_name):
            calls.append((Path(path), project_name))
            return SimpleNamespace(
                document=imported,
                audit=SimpleNamespace(to_dict=lambda: {"ready": True}),
            )

    monkeypatch.setattr(import_ui_runtime, "GraphicsImportService", FakeImportService)

    result = router.dispatch({"name": "import_pptx", "path": str(source)})

    assert result.ok and result.changed
    assert calls == [(source.resolve(), source.stem)]
    assert session.document is imported
    assert session.document.active_page_id == first_id
    assert len(session.document.pages) == 3
    assert session.selection == set()
    assert not session.history.can_undo
    assert result.payload["page_count"] == 3
    assert result.payload["active_page_id"] == first_id


def test_import_failure_preserves_current_canvas_and_returns_friendly_message(tmp_path, monkeypatch):
    source = tmp_path / "falha.pptx"
    source.write_bytes(b"broken-pptx")
    before = GraphicsDocument(name="Projeto atual")
    session = GraphicsSession(before)
    router = GraphicsCommandRouter(session)

    class FailingImportService:
        def import_file(self, path, *, project_name):
            raise RuntimeError("detalhe técnico de teste")

    monkeypatch.setattr(import_ui_runtime, "GraphicsImportService", FailingImportService)

    result = router.dispatch({"name": "import_pptx", "path": str(source)})

    assert not result.ok
    assert not result.changed
    assert result.message == "Não foi possível importar este arquivo PPTX."
    assert result.payload["technical_error"] == "RuntimeError: detalhe técnico de teste"
    assert session.document is before


def test_import_rejects_non_pptx_before_invoking_pipeline(tmp_path, monkeypatch):
    source = tmp_path / "arquivo.pdf"
    source.write_bytes(b"pdf")
    session = GraphicsSession(GraphicsDocument())
    router = GraphicsCommandRouter(session)

    class UnexpectedImportService:
        def import_file(self, path, *, project_name):
            raise AssertionError("pipeline não deve ser chamado para extensão inválida")

    monkeypatch.setattr(import_ui_runtime, "GraphicsImportService", UnexpectedImportService)

    result = router.dispatch({"name": "import_pptx", "path": str(source)})

    assert not result.ok
    assert not result.changed
    assert result.message == "Selecione um arquivo PowerPoint (.pptx)."
