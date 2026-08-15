from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.editor.controller import EditorController
from srstudio.editor.layout import Rect
from srstudio.editor.scene import Scene
from srstudio.editor.snap import SnapEngine
from srstudio.export.renderer import FlyerRenderer
from srstudio.templates.registry import TemplateRegistry


def test_scene_selection_duplicate_and_lock() -> None:
    project = StudioProject()
    page = project.pages[0]
    first = ProductCard(product_id="a", x=10, y=10)
    page.cards.append(first)
    scene = Scene(page)
    scene.selection.select(first.id)
    scene.lock_selected(True)
    scene.move_selected(50, 50)
    assert (first.x, first.y) == (10, 10)
    scene.lock_selected(False)
    duplicates = scene.duplicate_selected()
    assert len(duplicates) == 1
    assert duplicates[0].id != first.id


def test_snap_engine_aligns_centers() -> None:
    engine = SnapEngine(tolerance=10)
    moving = Rect(205, 100, 100, 100)
    other = Rect(100, 100, 100, 100)
    result = engine.snap(moving, [other], 600, 600)
    assert result.y == 100
    assert result.guides


def test_editor_controller_undo_add_and_layout() -> None:
    project = StudioProject()
    controller = EditorController(project)
    product = Product(original_name="ARROZ TESTE 5KG", price="19,99")
    controller.add_product(product)
    assert len(project.pages[0].cards) == 1
    controller.history.undo()
    assert len(project.pages[0].cards) == 0
    controller.history.redo()
    assert len(project.pages[0].cards) == 1
    controller.apply_auto_layout(highlighted=1)
    assert project.pages[0].cards[0].highlighted is True


def test_template_registry_seeds_defaults(tmp_path) -> None:
    registry = TemplateRegistry(tmp_path)
    registry.seed_defaults()
    templates = registry.list()
    assert len(templates) >= 6
    assert any(item.id == "quinta-file" for item in templates)


def test_renderer_creates_page_without_external_assets() -> None:
    project = StudioProject()
    product = Product(original_name="CAFÉ TESTE 500G", price="15,99")
    project.products.append(product)
    project.pages[0].cards.append(ProductCard(product_id=product.id, x=20, y=20, width=280, height=220))
    image = FlyerRenderer().render_page(project, project.pages[0], scale=0.25)
    assert image.size == (270, 338)
