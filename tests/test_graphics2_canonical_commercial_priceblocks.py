from __future__ import annotations

from srstudio.graphics2 import (
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    GraphicsSession,
    NodeKind,
    Transform,
    build_semantic_blocks,
)


def _text(text: str = "") -> GraphicsNode:
    return GraphicsNode(kind=NodeKind.TEXT, text=text, transform=Transform(width=160, height=50))


def test_canonical_retail_and_wholesale_roles_build_two_priceblocks_for_one_card():
    document = GraphicsDocument()
    page = document.active_page
    name = _text("ARROZ 5KG")
    retail = _text("R$ 24,90")
    wholesale = _text("R$ 22,50")
    quantity = _text("6")
    for node in (name, retail, wholesale, quantity):
        page.add_node(node)

    session = GraphicsSession(document)
    slot = session.create_slot(
        "Produto comercial",
        {
            BindingRole.NAME: name.id,
            BindingRole.RETAIL_PRICE: retail.id,
            BindingRole.WHOLESALE_PRICE: wholesale.id,
            BindingRole.QUANTITY: quantity.id,
        },
    )

    report = build_semantic_blocks(document)
    blocks = page.metadata["semantic_blocks"]
    price_blocks = [
        block
        for block in blocks.values()
        if block["kind"] == "price_block" and block["slot_id"] == slot.id
    ]
    cards = [
        block
        for block in blocks.values()
        if block["kind"] == "product_card" and block["slot_id"] == slot.id
    ]

    assert report.price_blocks == 2
    assert len(price_blocks) == 2
    assert len(cards) == 1
    primary = next(block for block in price_blocks if block["metadata"].get("commercial_role") != "wholesale")
    atacado = next(block for block in price_blocks if block["metadata"].get("commercial_role") == "wholesale")
    assert primary["roles"]["complete"] == [retail.id]
    assert atacado["roles"]["complete"] == [wholesale.id]
    assert set(cards[0]["metadata"]["price_blocks"]) == {primary["id"], atacado["id"]}
    assert quantity.id in cards[0]["members"]


def test_canonical_commercial_roles_bind_decimal_values_and_clear_absent_wholesale_quantity():
    document = GraphicsDocument()
    page = document.active_page
    name = _text()
    retail = _text()
    wholesale = _text()
    quantity = _text()
    for node in (name, retail, wholesale, quantity):
        page.add_node(node)

    session = GraphicsSession(document)
    slot = session.create_slot(
        "Produto comercial",
        {
            BindingRole.NAME: name.id,
            BindingRole.RETAIL_PRICE: retail.id,
            BindingRole.WHOLESALE_PRICE: wholesale.id,
            BindingRole.QUANTITY: quantity.id,
        },
    )

    assert session.bind_product(
        slot.id,
        {
            "id": "p1",
            "display_name": "FEIJÃO 1KG",
            "retail_price": "8.49",
            "wholesale_price": "7,29",
            "quantity": "6",
        },
    )
    assert name.text == "FEIJÃO 1KG"
    assert retail.text == "R$ 8,49"
    assert wholesale.text == "R$ 7,29"
    assert quantity.text == "6"

    assert session.bind_product(
        slot.id,
        {
            "id": "p2",
            "display_name": "FEIJÃO PREMIUM 1KG",
            "retail_price": "8,99",
        },
    )
    assert retail.text == "R$ 8,99"
    assert wholesale.text == ""
    assert wholesale.visible is False
    assert quantity.text == ""
    assert quantity.visible is False
