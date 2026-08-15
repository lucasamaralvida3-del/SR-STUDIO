from __future__ import annotations

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2 import BindingRole
from srstudio.graphics2.compat import from_studio_project, legacy_page_dict_to_graphics


def test_migrates_existing_product_card_to_semantic_slot():
    product = Product(display_name="CAFÉ VASCONCELOS 500G", price="19,98", unit="UN"); card = ProductCard(product_id=product.id, x=100, y=150, width=300, height=220); project = StudioProject(name="Encarte", products=[product], pages=[Page(cards=[card])])
    document = from_studio_project(project); page = document.active_page; assert card.id in page.nodes; assert len(page.slots) == 1; slot = next(iter(page.slots.values()))
    assert slot.node_id(BindingRole.NAME); assert slot.node_id(BindingRole.IMAGE); assert slot.node_id(BindingRole.PRICE_REAIS); assert slot.node_id(BindingRole.PRICE_CENTS); assert slot.node_id(BindingRole.UNIT)


def test_legacy_fidelity_layer_is_locked_background():
    page = legacy_page_dict_to_graphics({"id": "p1", "name": "Página 1", "width": 794, "height": 1123, "backgroundUrl": "/asset/design.png", "templateSlots": [{"id": "slot_1", "fields": {"NOME": {"x": 10, "y": 20, "w": 100, "h": 30, "style": {}}, "PRECO_REAIS": {"x": 10, "y": 50, "w": 50, "h": 50, "style": {}}}}]})
    background = next(node for node in page.nodes.values() if node.kind.value == "background"); assert background.locked is True; assert background.metadata["fidelity_layer"] is True; assert BindingRole.NAME.value in page.slots["slot_1"].node_by_role
