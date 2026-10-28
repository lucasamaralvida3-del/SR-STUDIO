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


def test_alpha_padded_campaign_seal_does_not_push_offers_down(tmp_path):
    from types import SimpleNamespace
    from PIL import Image, ImageDraw
    from srstudio.graphics2.model import Rect
    from srstudio.graphics2.campaign_tools import logo_safe_reserve
    path = tmp_path / "padded-logo.png"
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((40, 20, 360, 100), fill=(200, 20, 20, 255))
    image.save(path)
    seal = SimpleNamespace(
        visible=True,
        metadata={"campaign_art": "seal", "bound_image_source": str(path)},
        rect=Rect(380, 30, 620, 475),
        asset_id="",
    )
    page = SimpleNamespace(
        height=1350,
        metadata={"campaign_seal_node": "seal"},
        node=lambda _id: seal,
    )
    document = SimpleNamespace(assets={})
    original = logo_safe_reserve(page, .24)
    fixed = logo_safe_reserve(page, .24, document=document)
    assert original > .35
    assert fixed == .24


def test_release_keeps_betachannel_guarded_and_untouched_stable():
    # Protect the rollout from a stale Beta or a mistaken Stable promotion.
    script = (ROOT.parents[2] / "tools" / "promote_g2_beta65_launcher.py").read_text(encoding="utf-8")
    assert 'VERSION = "5.0.0-hybrid.g2beta.65"' in script
    assert 'base.get("version") != "5.0.0-hybrid.g2beta.64"' in script
    assert '"channel": "beta"' in script
    assert '"previous_version": base["version"]' in script
