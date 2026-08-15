from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.editor.pages import PageManager
from srstudio.intelligence.commands import CommandPlanner
from srstudio.validation.quality import QualityInspector


def test_page_manager_duplicates_and_renames() -> None:
    project = StudioProject()
    project.pages[0].cards.append(ProductCard(product_id="a"))
    manager = PageManager(project)
    clone = manager.duplicate(0)
    assert len(project.pages) == 2
    assert project.pages[0].name == "Página 1"
    assert clone.name == "Página 2"
    assert clone.cards[0].id != project.pages[0].cards[0].id


def test_page_manager_balances_cards() -> None:
    project = StudioProject()
    manager = PageManager(project)
    cards = [ProductCard(product_id=str(i)) for i in range(11)]
    pages = manager.distribute_cards(cards, capacity=4)
    assert [len(page.cards) for page in pages] == [4, 4, 3]


def test_quality_inspector_flags_missing_images() -> None:
    project = StudioProject()
    product = Product(original_name="TESTE", price="9,99")
    project.products.append(product)
    project.pages[0].cards.append(ProductCard(product_id=product.id, x=30, y=30))
    report = QualityInspector().inspect(project)
    image_metric = next(item for item in report.metrics if item.name == "Imagens")
    assert image_metric.score == 0
    assert 0 <= report.total <= 100


def test_command_planner_builds_safe_actions() -> None:
    planner = CommandPlanner()
    actions = planner.plan("Destaque o produto 3, aumente o preço 15% e reorganize a página")
    names = [item.action for item in actions]
    assert "highlight_product" in names
    assert "scale_price_style" in names
    assert "auto_layout" in names


def test_command_planner_requires_review_for_commercial_price() -> None:
    actions = CommandPlanner().plan("alterar preço desse produto")
    commercial = next(item for item in actions if item.action == "edit_commercial_price")
    assert commercial.requires_review is True
