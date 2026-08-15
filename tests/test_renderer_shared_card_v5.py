from srstudio.core.models import Product, ProductCard
from srstudio.export.renderer import FlyerRenderer


def test_render_card_layer_expands_when_rotated() -> None:
    product = Product(original_name="ARROZ TESTE 5KG", price="19,90", unit="UN")
    card = ProductCard(product_id=product.id, width=240, height=160, rotation=45)
    renderer = FlyerRenderer()

    plain = renderer.render_card_layer(card, product, scale=1.0, apply_rotation=False)
    rotated = renderer.render_card_layer(card, product, scale=1.0, apply_rotation=True)

    assert plain.size == (240, 160)
    assert rotated.width > plain.width
    assert rotated.height > plain.height


def test_render_card_layer_without_rotation_keeps_dimensions() -> None:
    product = Product(original_name="FEIJAO TESTE 1KG", price="8,99", unit="UN")
    card = ProductCard(product_id=product.id, width=220, height=140, rotation=0)
    layer = FlyerRenderer().render_card_layer(card, product, scale=1.0)
    assert layer.size == (220, 140)
