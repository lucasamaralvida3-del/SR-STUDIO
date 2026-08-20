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
        visible=True,
        transform=Transform(x=x, y=y, width=width, height=height),
        metadata={"source": "pptx", "source_name": name},
    )


def _wholesale_document() -> tuple[GraphicsDocument, dict[str, GraphicsNode]]:
    document = GraphicsDocument(name="Template varejo atacado")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    nodes = {
        "name": _text("SR_PRODUTO", "ARROZ TESTE 5KG", x=100, y=250, width=820, height=130),
        "retail_currency": _text("R$ VAREJO", "R$", x=80, y=520, width=90, height=55),
        "retail_price": _text("SR_PRECO_VAREJO", "24,90", x=190, y=500, width=520, height=145),
        "unit": _text("SR_UNIDADE_VAREJO", "CADA", x=720, y=560, width=130, height=60),
        "wholesale_currency": _text("R$ ATACADO", "R$", x=70, y=790, width=100, height=60),
        "wholesale_price": _text("SR_PRECO_ATACADO", "22,50", x=190, y=760, width=520, height=150),
        "quantity": _text("SR_QUANTIDADE_ATACADO", "6", x=720, y=820, width=140, height=70),
    }
    for node in nodes.values():
        page.add_node(node)
    return document, nodes


def test_named_retail_wholesale_fields_form_one_card_with_two_price_blocks():
    document, nodes = _wholesale_document()

    report = build_semantic_blocks(document)
    page = document.active_page

    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.metadata["explicit_named_semantics"] is True
    assert slot.metadata["explicit_named_semantics_version"] == 3
    assert slot.node_by_role["name"] == nodes["name"].id
    assert slot.node_by_role["price_complete"] == nodes["retail_price"].id
    assert slot.node_by_role["quantity"] == nodes["quantity"].id
    assert slot.metadata["extra_bindings"]["wholesale_price"] == [nodes["wholesale_price"].id]
    assert slot.metadata["extra_bindings"]["wholesale_price_currency"] == [nodes["wholesale_currency"].id]

    blocks = page.metadata["semantic_blocks"]
    price_blocks = [item for item in blocks.values() if item["kind"] == "price_block"]
    cards = [item for item in blocks.values() if item["kind"] == "product_card"]
    wholesale = [
        item
        for item in price_blocks
        if item["metadata"].get("commercial_role") == "wholesale"
    ]

    assert len(cards) == 1
    assert len(price_blocks) == 2
    assert len(wholesale) == 1
    assert report.price_blocks == 2
    assert document.metadata["commercial_price_blocks"]["wholesale_price_blocks"] == 1
    assert wholesale[0]["roles"]["complete"] == [nodes["wholesale_price"].id]
    assert wholesale[0]["roles"]["currency"] == [nodes["wholesale_currency"].id]
    assert wholesale[0]["id"] in cards[0]["metadata"]["price_blocks"]
    assert wholesale[0]["id"] in slot.metadata["semantic_price_block_ids"]


def test_wholesale_binding_updates_and_clears_optional_commercial_fields_with_undo_redo():
    document, nodes = _wholesale_document()
    build_semantic_blocks(document)
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    slot = next(iter(session.page.slots.values()))

    first = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot.id,
            "product": {
                "id": "produto-atacado-1",
                "display_name": "FEIJÃO 1KG",
                "price": "8,49",
                "retail_price": "8,49",
                "wholesale_price": "7,29",
                "quantity": "6",
                "unit": "UN",
            },
        }
    )

    assert first.ok and first.changed
    assert nodes["name"].text == "FEIJÃO 1KG"
    assert nodes["retail_currency"].text == "R$"
    assert nodes["retail_price"].text == "8,49"
    assert nodes["wholesale_currency"].text == "R$"
    assert nodes["wholesale_price"].text == "7,29"
    assert nodes["quantity"].text == "6"
    assert nodes["unit"].text == "CADA"

    second = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot.id,
            "product": {
                "id": "produto-varejo-2",
                "display_name": "FEIJÃO PREMIUM 1KG",
                "price": "8,99",
                "retail_price": "8,99",
                "unit": "UN",
            },
        }
    )

    assert second.ok and second.changed
    assert nodes["retail_price"].text == "8,99"
    assert nodes["wholesale_price"].text == ""
    assert nodes["wholesale_price"].visible is False
    assert nodes["wholesale_currency"].text == ""
    assert nodes["wholesale_currency"].visible is False
    assert nodes["quantity"].text == ""
    assert nodes["quantity"].visible is False

    assert session.undo() is True
    assert session.page.node(nodes["wholesale_price"].id).text == "7,29"
    assert session.page.node(nodes["wholesale_currency"].id).text == "R$"
    assert session.page.node(nodes["quantity"].id).text == "6"
    assert next(iter(session.page.slots.values())).product_id == "produto-atacado-1"

    assert session.redo() is True
    assert session.page.node(nodes["wholesale_price"].id).text == ""
    assert session.page.node(nodes["wholesale_currency"].id).text == ""
    assert next(iter(session.page.slots.values())).product_id == "produto-varejo-2"


def test_wholesale_semantic_build_is_idempotent():
    document, _ = _wholesale_document()

    first = build_semantic_blocks(document)
    page = document.active_page
    first_slot_ids = list(page.slots)
    first_blocks = set(page.metadata["semantic_blocks"])

    second = build_semantic_blocks(document)

    assert first.price_blocks == second.price_blocks == 2
    assert list(page.slots) == first_slot_ids
    assert set(page.metadata["semantic_blocks"]) == first_blocks
    assert len([
        item
        for item in page.metadata["semantic_blocks"].values()
        if item["kind"] == "price_block" and item["metadata"].get("commercial_role") == "wholesale"
    ]) == 1
