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


def _text(name: str, text: str, *, x: float, y: float, width: float, height: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=False,
        visible=True,
        transform=Transform(x=x, y=y, width=width, height=height),
        metadata={"source": "pptx", "source_name": name},
    )


def _two_price_document() -> tuple[GraphicsDocument, dict[str, GraphicsNode]]:
    document = GraphicsDocument(name="Template SR dois preços")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    nodes = {
        "name": _text("SR_PRODUTO", "WHISKY TESTE 1L", x=100, y=300, width=850, height=180),
        "currency": _text("WordArt 6", "R$", x=45, y=600, width=110, height=55),
        "unit": _text("SR_UNIDADE_PROMO", "CADA", x=20, y=690, width=150, height=70),
        "price": _text("SR_PRECO_PROMO", "92,77", x=195, y=580, width=720, height=185),
        "app_currency": _text("WordArt 6", "R$", x=35, y=880, width=115, height=70),
        "app_unit": _text("SR_UNIDADE_CLUBE", "CADA", x=15, y=1040, width=150, height=70),
        "app_price": _text("SR_PRECO_CLUBE", "89,64", x=190, y=895, width=750, height=250),
    }
    for node in nodes.values():
        page.add_node(node)
    return document, nodes


def test_named_sr_fields_form_one_product_card_with_two_price_blocks():
    document, nodes = _two_price_document()

    report = build_semantic_blocks(document)
    page = document.active_page

    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.metadata["explicit_named_semantics"] is True
    assert slot.metadata["source"] == "canva-smart-slot"
    assert slot.node_by_role["name"] == nodes["name"].id
    assert slot.node_by_role["price_complete"] == nodes["price"].id
    assert slot.node_by_role["price_currency"] == nodes["currency"].id
    assert slot.node_by_role["unit"] == nodes["unit"].id
    assert slot.metadata["extra_bindings"]["app_price_complete"] == [nodes["app_price"].id]
    assert slot.metadata["extra_bindings"]["app_price_currency"] == [nodes["app_currency"].id]
    assert slot.metadata["extra_bindings"]["app_unit"] == [nodes["app_unit"].id]

    blocks = list(page.metadata["semantic_blocks"].values())
    assert len([item for item in blocks if item["kind"] == "price_block"]) == 2
    assert len([item for item in blocks if item["kind"] == "product_card"]) == 1
    assert report.price_blocks == 1
    assert report.app_price_blocks == 1
    assert report.product_cards == 1
    assert report.recovered_price_blocks == 0
    assert report.recovered_smart_slots == 0


def test_named_two_price_slot_binds_product_without_duplicating_currency_and_supports_undo_redo():
    document, nodes = _two_price_document()
    build_semantic_blocks(document)
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    slot = next(iter(session.page.slots.values()))

    result = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot.id,
            "product": {
                "id": "prod-001",
                "name": "ARROZ TESTE 5KG",
                "price": "12.34",
                "app_price": "10.99",
                "unit": "UN",
            },
        }
    )

    assert result.ok is True
    assert result.changed is True
    assert slot.product_id == "prod-001"
    assert nodes["name"].text == "ARROZ TESTE 5KG"
    assert nodes["currency"].text == "R$"
    assert nodes["price"].text == "12,34"
    assert nodes["app_currency"].text == "R$"
    assert nodes["app_price"].text == "10,99"
    assert nodes["unit"].text == "CADA"
    assert nodes["app_unit"].text == "CADA"

    assert session.undo() is True
    assert session.page.node(nodes["price"].id).text == "92,77"
    assert session.page.node(nodes["app_price"].id).text == "89,64"
    assert next(iter(session.page.slots.values())).product_id == ""

    assert session.redo() is True
    assert session.page.node(nodes["price"].id).text == "12,34"
    assert session.page.node(nodes["app_price"].id).text == "10,99"
    assert next(iter(session.page.slots.values())).product_id == "prod-001"
