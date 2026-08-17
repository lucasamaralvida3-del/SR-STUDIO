from __future__ import annotations

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2 import BindingRole
from srstudio.graphics2.compat import from_studio_project, legacy_page_dict_to_graphics


def test_migrates_existing_product_card_to_semantic_slot_with_live_product_data():
    product = Product(
        display_name="CAFÉ VASCONCELOS 500G",
        price="19,98",
        unit="UN",
        image_path="C:/BancoSR/cafe.png",
    )
    card = ProductCard(product_id=product.id, x=100, y=150, width=300, height=220)
    project = StudioProject(name="Encarte", products=[product], pages=[Page(cards=[card])])

    document = from_studio_project(project)
    page = document.active_page
    assert card.id in page.nodes
    assert len(page.slots) == 1
    assert document.metadata["products"][0]["id"] == product.id
    assert document.metadata["graphics2_bridge_source"] == "studio-project-5x"

    slot = next(iter(page.slots.values()))
    name = page.node(slot.node_id(BindingRole.NAME))
    image = page.node(slot.node_id(BindingRole.IMAGE))
    reais = page.node(slot.node_id(BindingRole.PRICE_REAIS))
    cents = page.node(slot.node_id(BindingRole.PRICE_CENTS))
    unit = page.node(slot.node_id(BindingRole.UNIT))

    assert name and name.text == "CAFÉ VASCONCELOS 500G"
    assert image and image.metadata["bound_image_source"] == "C:/BancoSR/cafe.png"
    assert reais and reais.text == "19"
    assert cents and cents.text == ",98"
    assert unit and unit.text == "/UN"
    assert slot.product_id == product.id


def test_legacy_fidelity_layer_is_locked_background():
    page = legacy_page_dict_to_graphics(
        {
            "id": "p1",
            "name": "Página 1",
            "width": 794,
            "height": 1123,
            "backgroundUrl": "/asset/design.png",
            "templateSlots": [
                {
                    "id": "slot_1",
                    "fields": {
                        "NOME": {"x": 10, "y": 20, "w": 100, "h": 30, "style": {}},
                        "PRECO_REAIS": {"x": 10, "y": 50, "w": 50, "h": 50, "style": {}},
                    },
                }
            ],
        }
    )
    background = next(node for node in page.nodes.values() if node.kind.value == "background")
    assert background.locked is True
    assert background.metadata["fidelity_layer"] is True
    assert BindingRole.NAME.value in page.slots["slot_1"].node_by_role
