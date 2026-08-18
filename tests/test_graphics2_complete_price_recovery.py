from __future__ import annotations

from srstudio.graphics2 import (
    GraphicsCommandRouter,
    GraphicsDocument,
    GraphicsNode,
    GraphicsSession,
    NodeKind,
    Transform,
    build_semantic_blocks,
)


def _text(text: str, *, x: float, y: float, width: float, height: float, name: str) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        visible=True,
        locked=True,
        transform=Transform(x=x, y=y, width=width, height=height),
        metadata={"source": "pptx", "source_name": name},
    )


def test_complete_brazilian_price_with_cada_recovers_price_card_and_slot():
    """Fallback espacial continua funcionando quando o PPTX não nomeia os campos."""

    document = GraphicsDocument(name="Encarte real")
    page = document.active_page
    page.width = 1080
    page.height = 1350

    name = _text(
        "WHISKY JOHNNIE WALKER RED LABEL 1L",
        x=98,
        y=304,
        width=885,
        height=275,
        name="Text Box 1",
    )
    currency = _text("R$", x=43, y=617, width=113, height=50, name="WordArt 6")
    unit = _text("CADA", x=15, y=694, width=154, height=74, name="Text Box 3")
    price = _text("92,77", x=195, y=588, width=740, height=183, name="Text Box 2")
    for node in (name, currency, unit, price):
        page.add_node(node)

    report = build_semantic_blocks(document)

    blocks = page.metadata["semantic_blocks"]
    price_blocks = [item for item in blocks.values() if item["kind"] == "price_block"]
    product_cards = [item for item in blocks.values() if item["kind"] == "product_card"]

    assert report.recovered_price_blocks == 1
    assert len(price_blocks) == 1
    assert price_blocks[0]["roles"]["complete"] == [price.id]
    assert price_blocks[0]["roles"]["currency"] == [currency.id]
    assert price_blocks[0]["roles"]["unit"] == [unit.id]
    assert price_blocks[0]["metadata"]["complete_price_token"] is True
    assert len(product_cards) == 1
    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.metadata["semantic_recovered"] is True
    assert slot.node_by_role["name"] == name.id
    assert slot.node_by_role["retail_price"] == price.id
    assert slot.node_by_role["currency"] == currency.id
    assert slot.node_by_role["unit"] == unit.id


def test_recovered_complete_price_binds_through_real_command_router_without_losing_price():
    document = GraphicsDocument(name="Troca de produto")
    page = document.active_page
    page.width = 1080
    page.height = 1350

    name = _text("CAFÉ ORIGINAL 500G", x=120, y=300, width=720, height=120, name="Nome")
    currency = _text("R$", x=80, y=590, width=100, height=60, name="Moeda")
    unit = _text("CADA", x=70, y=700, width=140, height=70, name="Unidade")
    price = _text("19,90", x=220, y=570, width=600, height=180, name="Preço")
    for node in (name, currency, unit, price):
        page.add_node(node)

    build_semantic_blocks(document)
    slot = next(iter(page.slots.values()))
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    result = router.dispatch({
        "name": "bind_product",
        "slot_id": slot.id,
        "product": {
            "id": "cafe-2",
            "display_name": "CAFÉ PREMIUM 500G",
            "price": "21,49",
            "unit": "UN",
        },
    })

    assert result.ok is True
    assert result.changed is True
    assert slot.product_id == "cafe-2"
    assert name.text == "CAFÉ PREMIUM 500G"
    assert currency.text == "R$"
    assert price.text == "21,49"
    assert unit.text == "CADA"


def test_complete_price_recovery_does_not_promote_decimal_without_currency_and_unit():
    document = GraphicsDocument()
    page = document.active_page
    page.add_node(_text("TOTAL", x=100, y=100, width=200, height=40, name="label"))
    page.add_node(_text("92,77", x=100, y=180, width=200, height=60, name="number"))

    report = build_semantic_blocks(document)

    assert report.recovered_price_blocks == 0
    assert page.slots == {}
