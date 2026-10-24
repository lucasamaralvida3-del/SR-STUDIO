from pathlib import Path

def test_beta43_studio_uses_only_one_control_surface():
    qml=(Path(__file__).resolve().parents[1]/"src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    assert "header: null" in qml
    assert "Production Gate" not in qml
    assert "Ordem das páginas" not in qml
    assert 'text: "Importar Planilha / PPTX"' in qml
    assert 'text: "Salvar"' in qml
    assert 'text: "Recuperar"' in qml
    assert 'text: "Copiar"' in qml
    assert 'text: "Colar"' in qml
    assert 'text: "Exportar PDF"' in qml
    assert 'text: "Exportar PNG"' in qml
    assert 'text: "Adicionar página"' in qml
    assert 'id: sourceImportDialog' in qml


def test_beta43_import_actions_are_backed_by_real_host():
    host=(Path(__file__).resolve().parents[1]/"src/srstudio/graphics2/qt_host.py").read_text(encoding="utf-8")
    assert 'def importSource(self, raw_source: str) -> None:' in host
    assert "GraphicsImportService().import_file" in host
    assert "apply_stored_product_links(session.document)" in host
