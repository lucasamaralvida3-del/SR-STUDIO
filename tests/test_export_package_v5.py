from pathlib import Path

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.export.service import ExportService


def project_fixture() -> StudioProject:
    product = Product(original_name="CAFE TESTE 500G", price="15,99", unit="UN")
    page = Page(width=360, height=450, cards=[ProductCard(product_id=product.id, x=30, y=60, width=140, height=160)])
    return StudioProject(name="Campanha Teste", products=[product], pages=[page])


def test_export_pdf(tmp_path: Path) -> None:
    result = ExportService().export_pdf(project_fixture(), tmp_path / "campanha.pdf", scale=1.0, dpi=150)
    assert len(result.files) == 1
    assert result.files[0].suffix.lower() == ".pdf"
    assert result.files[0].exists()
    assert result.files[0].stat().st_size > 100


def test_social_variants_are_generated(tmp_path: Path) -> None:
    result = ExportService().export_social_variants(project_fixture(), tmp_path / "social")
    relative = [path.relative_to(tmp_path / "social").as_posix() for path in result.files]
    assert any(item.startswith("instagram/") for item in relative)
    assert any(item.startswith("whatsapp_status/") for item in relative)
    assert any(item.startswith("square/") for item in relative)


def test_campaign_package_contains_print_and_digital(tmp_path: Path) -> None:
    result = ExportService().export_campaign_package(project_fixture(), tmp_path / "package")
    suffixes = {path.suffix.lower() for path in result.files}
    assert ".pdf" in suffixes
    assert ".png" in suffixes
    assert len(result.files) >= 6
