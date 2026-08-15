from pathlib import Path

from PIL import Image

from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.images.quality import ImageQualityAnalyzer
from srstudio.projects.package import ProjectPackage
from srstudio.projects.proof import ProofManager
from srstudio.projects.store import ProjectStore


def test_project_package_roundtrip(tmp_path: Path) -> None:
    image_path = tmp_path / "produto.png"
    Image.new("RGB", (800, 800), "white").save(image_path)
    project = StudioProject(name="Teste portátil")
    product = Product(original_name="CAFE TESTE", price="9,99", image_path=str(image_path))
    project.products.append(product)
    project.pages[0].cards.append(ProductCard(product_id=product.id))
    store = ProjectStore(tmp_path / "autosave")
    service = ProjectPackage(store)
    package = service.create(project, tmp_path / "campanha.srpack")
    loaded = service.extract(package, tmp_path / "extracted")
    assert loaded.name == project.name
    assert Path(loaded.products[0].image_path).exists()


def test_proof_manager_tracks_page_approval() -> None:
    project = StudioProject()
    proof = ProofManager(project)
    assert proof.all_approved() is False
    proof.approve(project.pages[0].id, reviewer="Lucas")
    assert proof.all_approved() is True
    assert proof.pending_pages() == []
    proof.reject(project.pages[0].id, note="Revisar preço")
    assert proof.all_approved() is False


def test_image_quality_and_duplicates(tmp_path: Path) -> None:
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    image = Image.new("RGBA", (900, 900), (255, 255, 255, 0))
    image.save(first)
    second.write_bytes(first.read_bytes())
    analyzer = ImageQualityAnalyzer()
    report = analyzer.inspect(first)
    assert report.score == 100
    assert report.has_alpha is True
    duplicates = analyzer.duplicates([first, second])
    assert len(duplicates) == 1
