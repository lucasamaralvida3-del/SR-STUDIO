from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from srstudio.graphics2 import product_data_runtime
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage, SmartSlot
from srstudio.graphics2.operations import GraphicsSession


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ACTIONS = ROOT / "src" / "srstudio" / "graphics2" / "qml" / "ProjectActions.qml"


def _document(name: str, *, products: list[dict] | None = None, slot: bool = False) -> GraphicsDocument:
    page = GraphicsPage(id=f"page-{name}", name=name, width=1080, height=1350)
    if slot:
        page.slots["slot-1"] = SmartSlot(
            id="slot-1",
            name="Produto 1",
            page_id=page.id,
            metadata={"product_snapshot": {}, "effective_bounds": {"x": 10, "y": 20, "width": 300, "height": 400}},
        )
    document = GraphicsDocument(id=f"doc-{name}", name=name, pages=[page], active_page_id=page.id)
    document.metadata["products"] = deepcopy(products or [])
    return document


class _FakeImportService:
    def import_file(self, path, *, project_name=""):
        source = Path(path)
        if source.suffix.lower() in {".xlsx", ".xlsm"}:
            products = [
                {"id": "p-1", "display_name": "ARROZ TESTE", "price": "19.99", "unit": "UN"},
                {"id": "p-2", "display_name": "FEIJÃO TESTE", "price": "8.49", "unit": "UN"},
            ]
            return SimpleNamespace(document=_document("spreadsheet", products=products))
        if source.suffix.lower() == ".pptx":
            document = _document("template", slot=True)
            document.metadata["smart_slot_import_started_empty"] = True
            return SimpleNamespace(document=document)
        raise AssertionError(f"unexpected source: {source}")


def _router(monkeypatch, document: GraphicsDocument) -> tuple[GraphicsSession, GraphicsCommandRouter]:
    monkeypatch.setattr(product_data_runtime.import_bridge, "GraphicsImportService", _FakeImportService)
    session = GraphicsSession(document)
    return session, GraphicsCommandRouter(session)


def test_canva_then_spreadsheet_keeps_template_pages_and_loads_catalog(tmp_path, monkeypatch) -> None:
    template = tmp_path / "template.pptx"
    sheet = tmp_path / "produtos.xlsx"
    template.write_bytes(b"pptx")
    sheet.write_bytes(b"xlsx")
    session, router = _router(monkeypatch, _document("initial"))

    template_result = router.dispatch({"name": "import_template_source", "path": str(template)})
    assert template_result.ok is True
    assert session.document.name == "template"
    template_page_id = session.document.active_page_id
    assert "slot-1" in session.document.active_page.slots
    assert session.document.metadata["products"] == []

    sheet_result = router.dispatch({"name": "import_product_catalog", "path": str(sheet)})
    assert sheet_result.ok is True
    assert sheet_result.payload["products"] == 2
    assert sheet_result.payload["template_preserved"] is True
    assert session.document.active_page_id == template_page_id
    assert "slot-1" in session.document.active_page.slots
    assert [item["id"] for item in session.document.metadata["products"]] == ["p-1", "p-2"]


def test_spreadsheet_then_canva_preserves_catalog_and_replaces_only_layout(tmp_path, monkeypatch) -> None:
    template = tmp_path / "template.pptx"
    sheet = tmp_path / "produtos.xlsx"
    template.write_bytes(b"pptx")
    sheet.write_bytes(b"xlsx")
    session, router = _router(monkeypatch, _document("initial"))

    sheet_result = router.dispatch({"name": "import_product_catalog", "path": str(sheet)})
    assert sheet_result.ok is True
    assert len(session.document.metadata["products"]) == 2

    template_result = router.dispatch({"name": "import_template_source", "path": str(template)})
    assert template_result.ok is True
    assert template_result.payload["products_preserved"] == 2
    assert template_result.payload["template_started_empty"] is True
    assert session.document.name == "template"
    assert "slot-1" in session.document.active_page.slots
    assert [item["id"] for item in session.document.metadata["products"]] == ["p-1", "p-2"]
    assert session.document.metadata["product_catalog_source"].endswith("produtos.xlsx")


def test_project_actions_exposes_both_imports_in_normal_editor_flow() -> None:
    qml = PROJECT_ACTIONS.read_text(encoding="utf-8")
    assert 'objectName: "productionImportStrip"' in qml
    assert 'objectName: "importTemplateButton"' in qml
    assert 'text: "IMPORTAR CANVA / PPTX"' in qml
    assert 'objectName: "importSpreadsheetButton"' in qml
    assert 'text: "IMPORTAR PLANILHA"' in qml
    assert '"name":"import_template_source"' in qml
    assert '"name":"import_product_catalog"' in qml
