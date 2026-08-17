from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.product_card_edit import edit_product_card


def _session():
    document = GraphicsDocument(name="ProductCard editável")
    page = document.active_page
    nodes = {
        "name": GraphicsNode(kind=NodeKind.TEXT, text="PRODUTO ANTIGO", transform=Transform(x=30, y=20, width=240, height=40)),
        "image": GraphicsNode(kind=NodeKind.IMAGE, transform=Transform(x=30, y=70, width=220, height=170), style={"fit": "cover", "zoom": 1.2}),
        "currency": GraphicsNode(kind=NodeKind.TEXT, text="R$", transform=Transform(x=260, y=160, width=40, height=40)),
        "reais": GraphicsNode(kind=NodeKind.TEXT, text="12", transform=Transform(x=300, y=140, width=90, height=90)),
        "cents": GraphicsNode(kind=NodeKind.TEXT, text=",99", transform=Transform(x=390, y=145, width=50, height=40)),
        "unit": GraphicsNode(kind=NodeKind.TEXT, text="/KG", transform=Transform(x=390, y=190, width=50, height=35)),
        "limit": GraphicsNode(kind=NodeKind.TEXT, text="", visible=False, transform=Transform(x=30, y=250, width=260, height=30)),
        "app_currency": GraphicsNode(kind=NodeKind.TEXT, text="", visible=False, transform=Transform(x=260, y=250, width=40, height=35)),
        "app_reais": GraphicsNode(kind=NodeKind.TEXT, text="", visible=False, transform=Transform(x=300, y=240, width=80, height=60)),
        "app_cents": GraphicsNode(kind=NodeKind.TEXT, text="", visible=False, transform=Transform(x=380, y=245, width=50, height=35)),
    }
    for node in nodes.values():
        page.add_node(node)
    slot = SmartSlot(
        name="Produto 1",
        page_id=page.id,
        node_by_role={
            BindingRole.NAME.value: nodes["name"].id,
            BindingRole.IMAGE.value: nodes["image"].id,
            BindingRole.CURRENCY.value: nodes["currency"].id,
            BindingRole.PRICE_REAIS.value: nodes["reais"].id,
            BindingRole.PRICE_CENTS.value: nodes["cents"].id,
            BindingRole.UNIT.value: nodes["unit"].id,
            BindingRole.LIMIT.value: nodes["limit"].id,
        },
        metadata={
            "extra_bindings": {
                "app_price_currency": [nodes["app_currency"].id],
                "app_price_integer": [nodes["app_reais"].id],
                "app_price_cents": [nodes["app_cents"].id],
            },
            "product_snapshot": {"id": "produto-1", "price": "12,99", "unit": "KG"},
        },
    )
    page.slots[slot.id] = slot
    return GraphicsSession(document), slot.id, nodes


def test_edit_product_card_updates_fields_atomically_without_changing_geometry_or_image_framing():
    session, slot_id, nodes = _session()
    before_geometry = {key: deepcopy(node.transform) for key, node in nodes.items()}
    before_image_style = deepcopy(nodes["image"].style)

    assert edit_product_card(
        session,
        slot_id,
        name="LINGUIÇA MISTA CASEIRA SR",
        price="25,77",
        unit="UN",
        image_source="C:/produtos/linguica.png",
        limit="6UN",
        app_price="23,99",
    )

    assert session.page.node(nodes["name"].id).text == "LINGUIÇA MISTA CASEIRA SR"
    assert session.page.node(nodes["currency"].id).text == "R$"
    assert session.page.node(nodes["reais"].id).text == "25"
    assert session.page.node(nodes["cents"].id).text == ",77"
    assert session.page.node(nodes["unit"].id).text == "/UN"
    assert session.page.node(nodes["limit"].id).text == "LIMITE DE 6UN POR CPF"
    assert session.page.node(nodes["limit"].id).visible is True
    assert session.page.node(nodes["app_currency"].id).text == "R$"
    assert session.page.node(nodes["app_reais"].id).text == "23"
    assert session.page.node(nodes["app_cents"].id).text == ",99"
    assert session.page.node(nodes["image"].id).metadata["bound_image_source"].endswith("linguica.png")
    assert session.page.node(nodes["image"].id).style == before_image_style

    snapshot = session.page.slots[slot_id].metadata["product_snapshot"]
    assert snapshot["display_name"] == "LINGUIÇA MISTA CASEIRA SR"
    assert snapshot["price"] == "25,77"
    assert snapshot["app_price"] == "23,99"
    assert snapshot["unit"] == "UN"
    assert snapshot["limit"] == "6UN"

    for key, node in nodes.items():
        assert session.page.node(node.id).transform == before_geometry[key]


def test_edit_product_card_is_single_undoable_change():
    session, slot_id, nodes = _session()
    original = session.document.to_dict()

    assert edit_product_card(session, slot_id, name="NOVO PRODUTO", price="9,50", limit="")
    assert session.page.node(nodes["name"].id).text == "NOVO PRODUTO"
    assert session.page.node(nodes["limit"].id).visible is False

    assert session.undo()
    assert session.document.to_dict() == original


def test_edit_product_card_refuses_locked_slot_or_locked_member():
    session, slot_id, nodes = _session()
    session.page.slots[slot_id].locked = True
    assert not edit_product_card(session, slot_id, name="X")

    session, slot_id, nodes = _session()
    session.page.node(nodes["reais"].id).locked = True
    assert not edit_product_card(session, slot_id, price="10,00")
