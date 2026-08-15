from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.editor.controller import EditorController
from srstudio.editor.history import CommandHistory, LambdaCommand
from srstudio.editor.scene import Scene


def make_project() -> StudioProject:
    project = StudioProject(name="Premium Test")
    products = [Product(original_name=f"Produto {index}", price="9,99") for index in range(3)]
    project.products.extend(products)
    project.pages[0].cards = [
        ProductCard(product_id=products[0].id, x=100, y=100, width=200, height=140, z_index=0),
        ProductCard(product_id=products[1].id, x=390, y=180, width=180, height=140, z_index=1),
        ProductCard(product_id=products[2].id, x=700, y=260, width=160, height=140, z_index=2),
    ]
    return project


def test_resize_from_any_handle_changes_origin_and_size() -> None:
    project = make_project()
    scene = Scene(project.pages[0])
    card = project.pages[0].cards[0]
    scene.resize_from_handle(card.id, "nw", 60, 70)
    assert card.x == 60
    assert card.y == 70
    assert card.width == 240
    assert card.height == 170


def test_rotation_snaps_to_fifteen_degrees() -> None:
    project = make_project()
    scene = Scene(project.pages[0])
    card = project.pages[0].cards[0]
    scene.rotate(card.id, 23)
    assert card.rotation == 30


def test_alignment_and_distribution_operate_on_selection() -> None:
    project = make_project()
    scene = Scene(project.pages[0])
    scene.selection.ids = {card.id for card in project.pages[0].cards}
    scene.align_selected("top")
    assert {card.y for card in project.pages[0].cards} == {100}
    scene.distribute_selected("horizontal")
    cards = sorted(project.pages[0].cards, key=lambda item: item.x)
    first_gap = cards[1].x - (cards[0].x + cards[0].width)
    second_gap = cards[2].x - (cards[1].x + cards[1].width)
    assert round(first_gap, 5) == round(second_gap, 5)


def test_layer_visibility_and_order() -> None:
    project = make_project()
    scene = Scene(project.pages[0])
    card = project.pages[0].cards[0]
    scene.selection.select(card.id)
    scene.hide_selected(True)
    assert card.overrides["hidden"] is True
    scene.bring_selected_to_front()
    assert card.z_index == max(item.z_index for item in project.pages[0].cards)


def test_controller_rotation_is_undoable() -> None:
    project = make_project()
    controller = EditorController(project)
    card = project.pages[0].cards[0]
    controller.scene.selection.select(card.id)
    controller.rotate_selected(15)
    assert card.rotation == 15
    controller.history.undo()
    assert card.rotation == 0
    controller.history.redo()
    assert card.rotation == 15


def test_history_can_record_already_applied_live_transform() -> None:
    value = {"x": 20}
    history = CommandHistory()
    before = 10
    after = 20
    history.record(LambdaCommand("Mover ao vivo", lambda: value.update(x=after), lambda: value.update(x=before)))
    history.undo()
    assert value["x"] == before
    history.redo()
    assert value["x"] == after


def test_premium_modules_import_without_starting_tk() -> None:
    from srstudio.app.premium_editor import PremiumEncartesStudioView, PremiumFlyerCanvas
    from srstudio.app.ui_kit import IconButton, ToastManager, Tooltip

    assert PremiumEncartesStudioView is not None
    assert PremiumFlyerCanvas is not None
    assert IconButton is not None
    assert ToastManager is not None
    assert Tooltip is not None
