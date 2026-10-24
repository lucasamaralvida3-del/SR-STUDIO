from pathlib import Path


def test_beta42_reference_shell_and_bottom_pages():
    qml=(Path(__file__).resolve().parents[1]/"src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    for label in ("Produtos","Projeto",
                  "Produtos","Modelos","Elementos","Imagens","Texto",
                  "Formas","Fundos","Camadas","Buscar produtos",
                  "Todos os produtos","Ver mais produtos","Adicionar página",
                  "Importar PPTX / Planilha"):
        assert label in qml, label
    assert 'id: productList' in qml
    assert 'model: filteredProducts()' in qml
    assert '"name":"select_page"' in qml
    assert '"name":"add_page"' in qml
    assert "onMoved: window.zoom = value" in qml
    assert "exportPngDialog.open()" in qml
    assert "exportPdfDialog.open()" in qml
    assert "sceneBridge.attachProductImage(" in qml
    assert "function finishProductDrag" in qml
    assert "function createBlueSlot()" in qml
    assert "sceneBridge.saveSceneAs(selectedFile.toString())" in qml
    assert "sceneBridge.exportPng(selectedFile.toString())" in qml
