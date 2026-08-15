from pathlib import Path

from srstudio.assets.catalog import AssetCatalog
from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.diagnostics.audit import ProjectAudit
from srstudio.templates.learning import LayoutLearningEngine
from srstudio.workflows.professional import ProfessionalWorkflow


def test_layout_learning_roundtrip() -> None:
    project = StudioProject()
    product = Product(original_name="TESTE", price="9,99")
    project.products.append(product)
    card = ProductCard(product_id=product.id, x=100, y=200, width=300, height=400, highlighted=True)
    project.pages[0].cards.append(card)
    engine = LayoutLearningEngine()
    template = engine.learn_page(project.pages[0])
    card.x = 1
    card.y = 2
    card.highlighted = False
    applied = engine.apply(template, project.pages[0])
    assert applied == 1
    assert round(card.x) == 100
    assert round(card.y) == 200
    assert card.highlighted is True


def test_asset_catalog_deduplicates_by_checksum(tmp_path: Path) -> None:
    source = tmp_path / "logo.png"
    source.write_bytes(b"asset-test")
    catalog = AssetCatalog(tmp_path / "library")
    first = catalog.import_asset(source, "logos", ("sr",))
    second = catalog.import_asset(source, "logos", ("sr",))
    assert first.id == second.id
    assert len(catalog.records) == 1
    assert catalog.find(kind="logos", text="sr")


def test_project_audit_reports_orphans() -> None:
    project = StudioProject()
    used = Product(original_name="USADO", price="5,99")
    orphan = Product(original_name="ORFAO", price="6,99")
    project.products.extend([used, orphan])
    project.pages[0].cards.append(ProductCard(product_id=used.id, x=30, y=30))
    report = ProjectAudit().inspect(project)
    assert report.products == 2
    assert report.cards == 1
    assert report.orphan_products == 1


def test_professional_workflow_reviews_project() -> None:
    project = StudioProject()
    product = Product(original_name="CAFE TESTE 500G", price="15,99", unit="UN")
    project.products.append(product)
    project.pages[0].cards.append(ProductCard(product_id=product.id, x=30, y=30))
    result = ProfessionalWorkflow(project).review()
    assert result.stage == "review"
    assert "quality" in result.payload
