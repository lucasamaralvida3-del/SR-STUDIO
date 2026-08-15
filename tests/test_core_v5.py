from pathlib import Path

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.pricing.engine import PriceEngine
from srstudio.projects.store import ProjectStore
from srstudio.validation.engine import ValidationEngine
from srstudio.intelligence.actions import classify_action


def test_price_engine_splits_reais_and_centavos():
    parts = PriceEngine().split("1,98", "UN")
    assert parts.integer == "1"
    assert parts.cents == "98"
    assert parts.formatted == "R$ 1,98/UN"


def test_product_card_reference_validation():
    project = StudioProject(products=[Product(original_name="CAFÉ", price="10,99")])
    project.pages[0].cards.append(ProductCard(product_id="missing"))
    issues = ValidationEngine().validate_project(project)
    assert any(issue.code == "CARD_PRODUCT_BROKEN" for issue in issues)


def test_project_roundtrip(tmp_path: Path):
    product = Product(original_name="ARROZ 5KG", price="24,90", unit="UN", code="10")
    project = StudioProject(name="Teste", products=[product])
    project.pages[0].cards.append(ProductCard(product_id=product.id, x=10, y=20))
    store = ProjectStore(tmp_path / "autosave")
    path = store.save(project, tmp_path / "teste.srproject")
    loaded = store.load(path)
    assert loaded.name == "Teste"
    assert loaded.products[0].price == product.price
    assert loaded.pages[0].cards[0].product_id == product.id


def test_commercial_ai_actions_require_review():
    info = classify_action("change_price")
    assert info["commercial"] is True
    assert info["requires_review"] is True
