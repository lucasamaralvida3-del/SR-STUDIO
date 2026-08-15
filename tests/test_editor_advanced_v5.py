from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.editor.controller import EditorController
from srstudio.editor.groups import GroupEngine
from srstudio.editor.layers import LayersManager
from srstudio.editor.layout import Rect
from srstudio.editor.selection import SelectionGeometry
from srstudio.intelligence.commands import PlannedAction
from srstudio.intelligence.executor import IntelligenceExecutor


def test_layers_visibility_and_order():
    page = Page(cards=[ProductCard(product_id="a", z_index=0), ProductCard(product_id="b", z_index=1)])
    layers = LayersManager(page)
    first = page.cards[0]
    layers.bring_to_front(first.id)
    assert first.z_index == 1
    layers.set_visible(first.id, False)
    assert first.overrides["hidden"] is True
    layers.set_locked(first.id, True)
    assert first.locked is True


def test_group_alignment_and_distribution():
    cards = [
        ProductCard(x=0, y=0, width=100, height=100),
        ProductCard(x=160, y=30, width=100, height=100),
        ProductCard(x=400, y=70, width=100, height=100),
    ]
    engine = GroupEngine()
    engine.align_top(cards)
    assert {card.y for card in cards} == {0}
    engine.distribute_horizontal(cards)
    assert cards[0].x < cards[1].x < cards[2].x


def test_marquee_handles_resize_and_rotation():
    card = ProductCard(x=100, y=100, width=200, height=150)
    selected = SelectionGeometry.marquee([card], Rect(90, 90, 230, 180))
    assert card.id in selected
    assert len(SelectionGeometry.handles(card)) == 8
    SelectionGeometry.resize_from_handle(card, "se", 20, 30)
    assert card.width == 220
    assert card.height == 180
    SelectionGeometry.rotate(card, 17)
    assert card.rotation == 15


def test_intelligence_executor_requires_review_for_commercial_price():
    product = Product(original_name="Arroz 5kg", price="19,90")
    page = Page(cards=[ProductCard(product_id=product.id)])
    project = StudioProject(products=[product], pages=[page])
    editor = EditorController(project, page)
    executor = IntelligenceExecutor(project, editor)
    outcome = executor.execute(PlannedAction("edit_commercial_price", requires_review=True))
    assert outcome.applied is False
    assert "revisão" in outcome.message.lower()


def test_intelligence_executor_can_add_and_duplicate_page():
    product = Product(original_name="Feijão 1kg", price="7,99")
    project = StudioProject(products=[product], pages=[Page(cards=[ProductCard(product_id=product.id)])])
    editor = EditorController(project, project.pages[0])
    executor = IntelligenceExecutor(project, editor)
    assert executor.execute(PlannedAction("add_page")).applied
    assert len(project.pages) == 2
    assert executor.execute(PlannedAction("duplicate_page")).applied
    assert len(project.pages) == 3
