"""Production editor import must preserve an assembled flyer on XLSX import."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from srstudio.graphics2 import product_data_runtime
from srstudio.graphics2.campaign_tools import set_campaign_date
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.item_slots import create_item_slot
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.qt_host import import_into_open_editor


class _FakeService:
    def import_file(self, path, *, project_name=""):
        result = GraphicsDocument(name="Imported from " + Path(path).suffix)
        if Path(path).suffix == ".pptx":
            result.metadata["smart_slot_import_started_empty"] = True
        else:
            result.metadata["products"] = [
                {"id": "banana", "display_name": "BANANA PRATA",
                 "price": "3.89", "unit": "KG",
                 "validity": "27/10/2026"}]
        return SimpleNamespace(document=result)


def _source(tmp_path, ext):
    path = tmp_path / ("ofertas" + ext)
    path.write_bytes(b"fixture")
    return path


def _configured_router():
    session = GraphicsSession(GraphicsDocument(name="Meu encarte"))
    router = GraphicsCommandRouter(session)
    slot = create_item_slot(session, "individual-beta44")
    date = set_campaign_date(session, mode="auto")
    assert date == ""
    return session, router, slot.id


def test_xlsx_import_preserves_existing_art_and_refreshes_auto_date(tmp_path, monkeypatch):
    monkeypatch.setattr(product_data_runtime.import_bridge, "GraphicsImportService", _FakeService)
    sheet = _source(tmp_path, ".xlsx")
    session, router, slot_id = _configured_router()
    document = session.document
    page_id = session.page.id
    root_id = session.page.slots[slot_id].metadata["root_node_id"]
    date_id = session.page.metadata["campaign_date_node"]
    assert session.page.node(date_id).text == ""
    result = import_into_open_editor(session, router, sheet)
    assert result.ok, result.message
    assert session.document is document
    assert session.page.id == page_id
    assert slot_id in session.page.slots
    assert session.page.node(root_id) is not None
    assert session.page.node(date_id).text == "27/10/2026"
    assert session.document.metadata["products"][0]["id"] == "banana"


def test_manual_campaign_date_survives_sheet_import(tmp_path, monkeypatch):
    monkeypatch.setattr(product_data_runtime.import_bridge, "GraphicsImportService", _FakeService)
    sheet = _source(tmp_path, ".xlsx")
    session, router, _ = _configured_router()
    set_campaign_date(session, mode="manual", value="28/10/2026")
    result = import_into_open_editor(session, router, sheet)
    assert result.ok, result.message
    assert session.page.node(session.page.metadata["campaign_date_node"]).text == "28/10/2026"


def test_unexpected_extensions_cannot_clear_the_active_page(tmp_path):
    session, router, sid = _configured_router()
    csv = _source(tmp_path, ".csv")
    with pytest.raises(ValueError, match="XLSX"):
        import_into_open_editor(session, router, csv)
    assert sid in session.page.slots


def test_user_facing_import_chooses_safe_compatible_file_types():
    source = (Path(__file__).resolve().parents[1] /
              "src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text("utf-8")
    # Historical single-control shell remains intact; the Qt host now
    # routes each accepted type safely without introducing duplicate buttons.
    assert 'id: sourceImportDialog' in source
    assert 'text: "Importar PPTX / Planilha"' in source
    assert 'Excel/Canva (*.xlsx *.xlsm *.pptx)' in source
    assert 'XLSX/XLSM adiciona produtos sem apagar o encarte' in source
    assert 'id: spreadsheetImportDialog' not in source
    assert 'id: templateImportDialog' not in source
