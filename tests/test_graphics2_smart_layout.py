from __future__ import annotations

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.import_bridge import from_imported_project
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.smart_layout import LayoutOptions, SmartLayoutEngine


def test_auto_layout_moves_group_and_children_as_one_geometry():
    session = GraphicsSession(GraphicsDocument())
    page = session.page
    group = GraphicsNode(kind=NodeKind.GROUP, name="Produto", transform=Transform(x=100, y=100, width=200, height=200))
    page.add_node(group)
    child = GraphicsNode(kind=NodeKind.TEXT, name="Nome", text="CAFÉ", transform=Transform(x=120, y=120, width=160, height=40))
    page.add_node(child, parent_id=group.id)
    result = SmartLayoutEngine.auto_grid(
        session,
        [group.id],
        options=LayoutOptions(margin_left=0, margin_top=0, margin_right=0, margin_bottom=0, gap_x=0, gap_y=0, keep_size=False, fill_ratio=1.0),
    )
    assert result.moved == 1
    expected_y = (page.height - page.width) / 2
    assert group.transform.x == 0
    assert group.transform.y == expected_y
    assert group.transform.width == page.width
    assert group.transform.height == page.width
    assert child.transform.x == page.width * 0.1
    assert child.transform.y == expected_y + page.width * 0.1
    assert child.transform.width == page.width * 0.8
    assert child.transform.height == page.width * 0.2


def test_auto_layout_keeps_fidelity_layer_untouched():
    session = GraphicsSession(GraphicsDocument())
    page = session.page
    background = GraphicsNode(kind=NodeKind.BACKGROUND, locked=True, transform=Transform(x=0, y=0, width=page.width, height=page.height), metadata={"fidelity_layer": True})
    page.add_node(background)
    result = SmartLayoutEngine.auto_grid(session)
    assert result.moved == 0
    assert background.transform.width == page.width


def test_fill_smart_slots_uses_visual_order_and_split_price():
    products = [
        Product(display_name="ACÉM BOVINO", price="33,64", unit="KG"),
        Product(display_name="COXA E SOBRECOXA", price="8,79", unit="KG"),
    ]
    cards = [ProductCard(id="slot_1"), ProductCard(id="slot_2")]
    page = Page(cards=cards, elements=[])
    for index, card in enumerate(cards):
        x = 50 + index * 300
        page.elements.extend([
            {"type": "text", "x": x, "y": 100, "width": 220, "height": 35, "text": "NOME", "slot_id": card.id, "slot_role": "name"},
            {"type": "text", "x": x, "y": 220, "width": 100, "height": 70, "text": "0", "slot_id": card.id, "slot_role": "price_integer"},
            {"type": "text", "x": x + 100, "y": 220, "width": 55, "height": 35, "text": ",00", "slot_id": card.id, "slot_role": "price_cents"},
        ])
    document = from_imported_project(StudioProject(products=products, pages=[page]))
    session = GraphicsSession(document)
    applied = SmartLayoutEngine.fill_smart_slots(session, [product.to_dict() for product in products])
    assert applied == 2
    first = session.page.slots["slot_1"]
    second = session.page.slots["slot_2"]
    assert session.page.node(first.node_by_role[BindingRole.NAME.value]).text == "ACÉM BOVINO"
    assert session.page.node(first.node_by_role[BindingRole.PRICE_REAIS.value]).text == "33"
    assert session.page.node(first.node_by_role[BindingRole.PRICE_CENTS.value]).text == ",64"
    assert session.page.node(second.node_by_role[BindingRole.NAME.value]).text == "COXA E SOBRECOXA"
    assert session.page.node(second.node_by_role[BindingRole.PRICE_REAIS.value]).text == "8"
    assert session.page.node(second.node_by_role[BindingRole.PRICE_CENTS.value]).text == ",79"
