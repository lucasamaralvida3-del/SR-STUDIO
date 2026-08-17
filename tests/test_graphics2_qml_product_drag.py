from __future__ import annotations

from pathlib import Path

import srstudio.graphics2.qt_host as qt_host


def _qml_source() -> str:
    path = Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml"
    return path.read_text(encoding="utf-8")


def test_qml_exposes_physical_product_drag_contract():
    source = _qml_source()
    assert "property bool productDragActive" in source
    assert "property string dragHoverSlotId" in source
    assert "function beginProductDrag" in source
    assert "function updateProductDrag" in source
    assert "function finishProductDrag" in source
    assert '"name": "drop_product"' in source
    assert '"magnet_distance"' in source


def test_qml_highlights_semantic_smart_slot_during_drag():
    source = _qml_source()
    assert "semantic_product_card_id" in source
    assert "function slotAtDocumentPoint" in source
    assert "property bool isDropTarget" in source
    assert "SOLTAR PRODUTO AQUI" in source
    assert "Solte para aplicar o produto" in source


def test_qml_drag_ghost_keeps_product_identity_visible():
    source = _qml_source()
    assert "id: productDragGhost" in source
    assert "productLabel(draggedProduct)" in source
    assert "draggedProduct.image_path" in source
