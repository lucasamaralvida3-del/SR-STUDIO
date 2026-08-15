from __future__ import annotations

from decimal import Decimal

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.editor.controller import EditorController
from srstudio.editor.detected_slots import DetectedSlotService


def _slot_fixture(tmp_path):
    old_image = tmp_path / "old.png"
    old_image.write_bytes(b"old")
    page = Page()
    template = Product(original_name="ARROZ ANTIGO", price=Decimal("10.50"), unit="KG", image_path=str(old_image))
    card = ProductCard(
        product_id=template.id,
        x=40,
        y=70,
        width=240,
        height=180,
        overrides={
            "slot_detected": True,
            "slot_validated": True,
            "slot_filled": False,
            "slot_template_product_id": template.id,
            "hidden": True,
            "recognition_confidence": 0.92,
        },
    )
    page.cards.append(card)
    page.elements.extend(
        [
            {"type": "text", "text": "ARROZ ANTIGO", "template_text": "ARROZ ANTIGO", "slot_id": card.id, "slot_role": "name"},
            {"type": "image", "path": str(old_image), "template_path": str(old_image), "slot_id": card.id, "slot_role": "image"},
            {"type": "text", "text": "R$", "template_text": "R$", "slot_id": card.id, "slot_role": "price_currency"},
            {"type": "text", "text": "10", "template_text": "10", "slot_id": card.id, "slot_role": "price_integer"},
            {"type": "text", "text": ",50", "template_text": ",50", "slot_id": card.id, "slot_role": "price_cents"},
            {"type": "text", "text": "/KG", "template_text": "/KG", "slot_id": card.id, "slot_role": "unit"},
            {"type": "text", "text": "9", "template_text": "9", "slot_id": card.id, "slot_role": "app_price_integer"},
        ]
    )
    project = StudioProject(products=[template], pages=[page])
    return project, page, card, template


def test_detected_slot_updates_native_canva_elements_and_undoes(tmp_path):
    project, page, card, template = _slot_fixture(tmp_path)
    new_image = tmp_path / "new.png"
    new_image.write_bytes(b"new")
    product = Product(
        original_name="FEIJAO NOVO 1KG",
        price=Decimal("7.49"),
        app_price=Decimal("6.99"),
        unit="UN",
        image_path=str(new_image),
    )
    project.products.append(product)
    controller = EditorController(project, page)

    assert DetectedSlotService.fill_with_history(controller, card, product)
    bound = {element["slot_role"]: element for element in page.elements}
    assert card.product_id == product.id
    assert card.overrides["slot_filled"] is True
    assert card.locked is True
    assert bound["name"]["text"] == "FEIJAO NOVO 1KG"
    assert bound["image"]["path"] == str(new_image)
    assert bound["price_currency"]["text"] == "R$"
    assert bound["price_integer"]["text"] == "7"
    assert bound["price_cents"]["text"] == ",49"
    assert bound["unit"]["text"] == "/UN"
    assert bound["app_price_integer"]["text"] == "6"

    controller.history.undo()
    bound = {element["slot_role"]: element for element in page.elements}
    assert card.product_id == template.id
    assert card.overrides["slot_filled"] is False
    assert bound["name"]["text"] == "ARROZ ANTIGO"
    assert bound["image"]["path"].endswith("old.png")
    assert bound["price_integer"]["text"] == "10"


def test_detected_slot_hides_secondary_price_and_image_when_product_has_no_image(tmp_path):
    project, page, card, _template = _slot_fixture(tmp_path)
    product = Product(original_name="OLEO 900ML", price=Decimal("6.99"), unit="UN")
    project.products.append(product)
    controller = EditorController(project, page)

    assert DetectedSlotService.fill_with_history(controller, card, product)
    secondary = next(element for element in page.elements if element["slot_role"] == "app_price_integer")
    image = next(element for element in page.elements if element["slot_role"] == "image")
    assert secondary["hidden"] is True
    assert image["path"] == ""
    assert image["hidden"] is True


def test_next_empty_slot_uses_visual_order_and_skips_filled(tmp_path):
    project, page, first, _template = _slot_fixture(tmp_path)
    second = ProductCard(
        product_id=first.product_id,
        x=10,
        y=300,
        width=220,
        height=170,
        overrides={
            "slot_detected": True,
            "slot_validated": True,
            "slot_filled": False,
            "hidden": True,
            "recognition_confidence": 0.9,
        },
    )
    page.cards.append(second)
    page.elements.extend(
        [
            {"type": "text", "text": "X PRODUTO", "template_text": "X PRODUTO", "slot_id": second.id, "slot_role": "name"},
            {"type": "text", "text": "5", "template_text": "5", "slot_id": second.id, "slot_role": "price_integer"},
            {"type": "text", "text": ",90", "template_text": ",90", "slot_id": second.id, "slot_role": "price_cents"},
        ]
    )

    assert DetectedSlotService.next_empty(page) is first
    first.overrides["slot_filled"] = True
    assert DetectedSlotService.next_empty(page) is second
    second.overrides["slot_filled"] = True
    assert DetectedSlotService.next_empty(page) is None


def test_giant_or_incomplete_detected_region_is_not_fillable(tmp_path):
    _project, page, _first, _template = _slot_fixture(tmp_path)
    giant = ProductCard(
        x=5,
        y=5,
        width=1000,
        height=1100,
        overrides={"slot_detected": True, "recognition_confidence": 0.99, "hidden": True},
    )
    page.cards.append(giant)
    page.elements.extend(
        [
            {"type": "text", "text": "ACEM", "slot_id": giant.id, "slot_role": "name"},
            {"type": "text", "text": "33", "slot_id": giant.id, "slot_role": "price_integer"},
            {"type": "text", "text": ",64", "slot_id": giant.id, "slot_role": "price_cents"},
        ]
    )
    incomplete = ProductCard(
        x=300,
        y=300,
        width=180,
        height=150,
        overrides={"slot_detected": True, "recognition_confidence": 0.99, "hidden": True},
    )
    page.cards.append(incomplete)
    page.elements.append({"type": "text", "text": "SEM PRECO", "slot_id": incomplete.id, "slot_role": "name"})

    assert DetectedSlotService.can_fill(page, giant) is False
    assert DetectedSlotService.can_fill(page, incomplete) is False


def test_clear_slot_restores_original_canva_content(tmp_path):
    project, page, card, template = _slot_fixture(tmp_path)
    product = Product(original_name="CAFE 500G", price=Decimal("18.90"), unit="UN")
    project.products.append(product)
    controller = EditorController(project, page)
    DetectedSlotService.fill_with_history(controller, card, product)

    assert DetectedSlotService.clear_with_history(controller, card)
    assert card.product_id == template.id
    assert card.overrides["slot_filled"] is False
    name = next(element for element in page.elements if element["slot_role"] == "name")
    assert name["text"] == "ARROZ ANTIGO"
