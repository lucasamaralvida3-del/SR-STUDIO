from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.export.renderer import FlyerRenderer


def test_renderer_skips_hidden_card():
    product = Product(original_name="Produto", price="9,99")
    hidden = ProductCard(product_id=product.id, x=10, y=10, width=100, height=80)
    hidden.overrides["hidden"] = True
    page = Page(width=300, height=300, cards=[hidden])
    project = StudioProject(products=[product], pages=[page])
    image = FlyerRenderer().render_page(project, page)
    assert image.size == (300, 300)


def test_renderer_supports_rotation_and_price_scale():
    product = Product(original_name="Produto", price="19,90")
    card = ProductCard(product_id=product.id, x=40, y=40, width=140, height=120, rotation=15)
    card.overrides["price_scale"] = 1.2
    page = Page(width=300, height=300, cards=[card])
    project = StudioProject(products=[product], pages=[page])
    image = FlyerRenderer().render_page(project, page)
    assert image.size == (300, 300)
