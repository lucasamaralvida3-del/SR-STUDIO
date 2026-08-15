from pathlib import Path

from srstudio.core.models import Product, StudioProject
from srstudio.products.database import ProductDatabase
from srstudio.products.sync import ProductKnowledgeSync


def test_product_knowledge_sync_records_product_and_price(tmp_path: Path) -> None:
    database = ProductDatabase(tmp_path / "products.sqlite3")
    project = StudioProject(name="Campanha", campaign="Quinta Filé")
    project.products.append(
        Product(
            code="123",
            ean="7890000000001",
            original_name="PRODUTO TESTE 1KG",
            display_name="Produto Teste 1KG",
            price="19,99",
            unit="UN",
            category="Teste",
        )
    )
    result = ProductKnowledgeSync(database).sync_project(project)
    assert result.products == 1
    assert result.prices_recorded == 1
    found = database.search("PRODUTO TESTE")
    assert len(found) == 1
    assert found[0]["ean"] == "7890000000001"
    history = database.price_history("7890000000001")
    assert history[0]["price"] == "19.99"
