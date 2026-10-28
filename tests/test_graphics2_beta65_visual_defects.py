"""Regression checks for reported Beta64 visual defects.

The source-level controls below supplement (not replace) live Windows screenshots.
In particular, missing SKU photos may not be silently invented or replaced.
"""
from pathlib import Path

from srstudio.graphics2 import __file__ as root_module


ROOT = Path(root_module).parent
QML = (ROOT / "qml" / "GraphicsEditor.qml").read_text(encoding="utf-8")


def test_narrow_product_sidebar_puts_actions_on_second_row():
    assert 'height: Math.max(184, productInformation.implicitHeight + 80)' in QML
    assert "Layout.preferredWidth: productCard.width < 285 ? 60 : 76" in QML
    assert 'text: "Inativo neste encarte"' not in QML  # status must reflect state
    assert 'productCard.inactive ? "Inativo neste encarte"' in QML
    assert 'text: "−"' in QML
    assert 'enabled: !productCard.inactive' in QML
    assert 'window.highlightedProduct(productCard.productData) ? "#E6A500"' in QML
    assert "elide: Text.ElideRight" in QML


def test_thumbnails_consider_more_than_first_28_document_nodes():
    assert ".slice(0, 28)" not in QML
    assert ".slice(0, 260)" in QML
    assert "n.kind !== \"group\"" in QML
    assert '("Pág. " + (index + 1))' in QML


def test_preflight_warns_about_missing_product_photos_before_build():
    assert "produto(s) sem foto confirmada" in QML
    assert 'window.productImageState(p) !== "linked"' in QML
    assert "Use Banco SR ou adicione fotos antes de confirmar." in QML


def test_photo_removal_precedes_slot_background_removal():
    code = QML.split("    function removeCurrentBackground() {", 1)[1].split("\n    }", 1)[0]
    assert code.index("if (selectedPicture())") < code.index('else if (selectedSlotId !== "")')
    assert 'sceneBridge.removeBackground(modelData.id)' in QML


def test_image_replacement_stays_manual_for_unavailable_photos():
    # Distinguish missing photos in the UI, avoid choosing a random product.
    assert '"Sem imagem disponível"' in QML
    assert '"Banco SR"' in QML
