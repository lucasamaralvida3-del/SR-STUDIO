from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks, semantic_block


def _text(name: str, text: str, x: float, y: float, w: float, h: float, *, font_size: float = 34) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": font_size},
        metadata={"source_name": name},
    )


def _image(name: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.IMAGE,
        name=name,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        metadata={"source_name": name},
    )


def _add_price(page, prefix: str, x: float, y: float, whole: str, cents: str = ",77"):
    currency = _text(f"{prefix} Currency", "R$", x, y + 40, 40, 55, font_size=28)
    integer = _text(f"{prefix} Whole", whole, x + 42, y, 110, 115, font_size=82)
    cent = _text(f"{prefix} Cents", cents, x + 150, y + 8, 50, 42, font_size=31)
    unit = _text(f"{prefix} Unit", "KG", x + 150, y + 60, 50, 38, font_size=28)
    for node in (currency, integer, cent, unit):
        page.add_node(node)
    return currency, integer, cent, unit


def test_ungrouped_canva_card_is_recovered_spatially_and_promoted_to_slot():
    document = GraphicsDocument(name="Canva sem grupos")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    name = _text("TextBox Name", "LINGUIÇA MISTA CASEIRA SR", 620, 770, 330, 70, font_size=39)
    image = _image("Freeform Product Image", 650, 850, 260, 175)
    currency, whole, cents, unit = _add_price(page, "P1", 700, 1030, "25")
    disclaimer = _text(
        "TextBox Disclaimer",
        "( OFERTAS VÁLIDAS SOMENTE PARA SANTA JULIANA )",
        90,
        320,
        900,
        30,
        font_size=18,
    )
    date = _text("TextBox Date", "13/08/2026", 80, 360, 180, 30, font_size=20)
    for node in (name, image, disclaimer, date):
        page.add_node(node)
    before = {node.id: deepcopy(node.transform) for node in page.nodes.values()}

    report = build_semantic_blocks(document)

    assert report.recovered_price_blocks == 1
    assert report.recovered_product_cards == 1
    assert report.recovered_group_product_cards == 0
    assert report.recovered_spatial_product_cards == 1
    assert report.recovered_smart_slots == 1
    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.metadata["recovered_spatial"] is True
    assert slot.metadata["recovered_from_pptx_group"] is False
    assert slot.name == "LINGUIÇA MISTA CASEIRA SR"
    assert slot.node_by_role["name"] == name.id
    assert slot.node_by_role["image"] == image.id
    assert slot.node_by_role["currency"] == currency.id
    assert slot.node_by_role["price_reais"] == whole.id
    assert slot.node_by_role["price_cents"] == cents.id
    assert slot.node_by_role["unit"] == unit.id
    card_id = name.metadata["semantic_product_card_id"]
    card = semantic_block(page, card_id)
    assert card is not None
    assert card["metadata"]["source"] == "spatial-card-recovery"
    assert card["metadata"]["spatial"] is True
    assert disclaimer.id not in card["members"]
    assert date.id not in card["members"]
    assert "semantic_product_card_id" not in disclaimer.metadata
    assert "semantic_product_card_id" not in date.metadata
    for node_id, transform in before.items():
        assert page.node(node_id).transform == transform


def test_spatial_recovery_keeps_adjacent_grid_cards_separate():
    document = GraphicsDocument(name="Grade Canva")
    page = document.active_page
    page.width = 1200
    page.height = 1500

    left_name = _text("Left Name", "ACÉM BOVINO", 90, 760, 300, 60)
    left_image = _image("Left Image", 110, 850, 250, 170)
    left_price = _add_price(page, "Left", 130, 1060, "24", ",98")

    right_name = _text("Right Name", "PONTA DE PICANHA NELORE", 700, 760, 330, 60)
    right_image = _image("Right Image", 730, 850, 250, 170)
    right_price = _add_price(page, "Right", 760, 1060, "44", ",79")

    for node in (left_name, left_image, right_name, right_image):
        page.add_node(node)

    report = build_semantic_blocks(document)

    assert report.recovered_price_blocks == 2
    assert report.recovered_spatial_product_cards == 2
    assert report.recovered_smart_slots == 2
    slots = {slot.name: slot for slot in page.slots.values()}
    assert set(slots) == {"ACÉM BOVINO", "PONTA DE PICANHA NELORE"}
    left_slot = slots["ACÉM BOVINO"]
    right_slot = slots["PONTA DE PICANHA NELORE"]
    assert left_slot.node_by_role["name"] == left_name.id
    assert left_slot.node_by_role["image"] == left_image.id
    assert left_slot.node_by_role["price_reais"] == left_price[1].id
    assert right_slot.node_by_role["name"] == right_name.id
    assert right_slot.node_by_role["image"] == right_image.id
    assert right_slot.node_by_role["price_reais"] == right_price[1].id
    assert left_name.metadata["semantic_product_card_id"] != right_name.metadata["semantic_product_card_id"]


def test_spatial_card_binding_changes_content_without_changing_template_geometry():
    document = GraphicsDocument(name="Binding espacial")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    name = _text("Name", "PRODUTO ANTIGO", 120, 690, 300, 65)
    image = _image("Image", 150, 780, 260, 170)
    currency, whole, cents, unit = _add_price(page, "Price", 190, 1010, "18", ",63")
    for node in (name, image):
        page.add_node(node)
    report = build_semantic_blocks(document)
    assert report.recovered_smart_slots == 1
    slot = next(iter(page.slots.values()))
    before = {node.id: deepcopy(node.transform) for node in page.nodes.values()}
    document.metadata["products"] = [
        {
            "id": "new-product",
            "display_name": "PÃO DE QUEIJO CONGELADO SR 1KG",
            "price": "19,89",
            "unit": "UN",
            "image_path": "/tmp/pao-queijo.png",
        }
    ]
    router = GraphicsCommandRouter(GraphicsSession(document))

    result = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product_id": "new-product"})

    assert result.ok and result.changed
    assert page.node(name.id).text == "PÃO DE QUEIJO CONGELADO SR 1KG"
    assert page.node(currency.id).text == "R$"
    assert page.node(whole.id).text == "19"
    assert page.node(cents.id).text == ",89"
    assert page.node(unit.id).text == "/UN"
    assert page.node(image.id).metadata["bound_image_source"] == "/tmp/pao-queijo.png"
    for node_id, transform in before.items():
        assert page.node(node_id).transform == transform


def test_spatial_build_is_idempotent_and_restores_lock_state_before_rebuild():
    document = GraphicsDocument(name="Idempotência espacial")
    page = document.active_page
    name = _text("Name", "COSTELA RIPA", 100, 600, 280, 55)
    image = _image("Image", 120, 680, 240, 160)
    _add_price(page, "Price", 150, 900, "33", ",64")
    for node in (name, image):
        page.add_node(node)

    first = build_semantic_blocks(document)
    first_slot_ids = list(page.slots)
    first_card_id = name.metadata["semantic_product_card_id"]
    second = build_semantic_blocks(document)

    assert first.recovered_spatial_product_cards == second.recovered_spatial_product_cards == 1
    assert first.recovered_smart_slots == second.recovered_smart_slots == 1
    assert list(page.slots) == first_slot_ids
    assert name.metadata["semantic_product_card_id"] == first_card_id
    assert name.locked is False
    assert image.locked is False
