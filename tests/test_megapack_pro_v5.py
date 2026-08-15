from srstudio.app.commands import CommandRegistry, StudioCommand
from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.editor.adaptation import FORMATS, FormatAdaptationEngine
from srstudio.editor.bulk import BulkOperations
from srstudio.intelligence.suggestions import SuggestionEngine


def project_with_card() -> StudioProject:
    project = StudioProject()
    product = Product(original_name="ARROZ TESTE 5KG", price="19,99", unit="UND")
    project.products.append(product)
    project.pages[0].cards.append(ProductCard(product_id=product.id, x=40, y=40, width=250, height=300))
    return project


def test_bulk_operations_normalize_and_scale() -> None:
    project = project_with_card()
    bulk = BulkOperations(project)
    assert bulk.normalize_units().affected == 1
    assert project.products[0].unit == "UN"
    assert bulk.set_price_scale(1.25).affected == 1
    assert project.pages[0].cards[0].overrides["price_scale"] == 1.25


def test_format_adaptation_changes_geometry() -> None:
    project = project_with_card()
    adapted = FormatAdaptationEngine().adapt(project.pages[0], "whatsapp_status")
    assert adapted.width == FORMATS["whatsapp_status"].width
    assert adapted.height == FORMATS["whatsapp_status"].height
    assert adapted.id != project.pages[0].id
    assert len(adapted.cards) == 1


def test_suggestion_engine_returns_actionable_items() -> None:
    project = project_with_card()
    items = SuggestionEngine().suggest(project)
    assert items
    assert all(item.action for item in items)


def test_command_registry_executes_handler() -> None:
    registry = CommandRegistry()
    called = []
    registry.register(StudioCommand("x", "Executar", "Teste", handler=lambda: called.append(True)))
    registry.execute("x")
    assert called == [True]
