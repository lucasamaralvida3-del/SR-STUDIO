from __future__ import annotations

from hashlib import sha1

from srstudio.graphics2 import GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform, build_semantic_blocks


def _text(name: str, text: str, *, x: float, y: float, width: float, height: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        visible=True,
        transform=Transform(x=x, y=y, width=width, height=height),
        metadata={"source": "pptx", "source_name": name},
    )


def _named_nodes(document: GraphicsDocument) -> dict[str, GraphicsNode]:
    page = document.active_page
    page.width = 1080
    page.height = 1350
    nodes = {
        "name": _text("SR_PRODUTO", "ARROZ 5KG", x=100, y=250, width=800, height=110),
        "retail_currency": _text("Moeda varejo", "R$", x=70, y=510, width=90, height=55),
        "retail": _text("SR_PRECO_VAREJO", "24,90", x=190, y=490, width=500, height=140),
        "unit": _text("SR_UNIDADE_VAREJO", "CADA", x=720, y=540, width=120, height=60),
        "wholesale_currency": _text("Moeda atacado", "R$", x=70, y=780, width=90, height=55),
        "wholesale": _text("SR_PRECO_ATACADO", "22,50", x=190, y=750, width=500, height=145),
        "quantity": _text("SR_QUANTIDADE_ATACADO", "6", x=720, y=800, width=130, height=60),
    }
    for node in nodes.values():
        page.add_node(node)
    return nodes


def test_fresh_named_slot_preserves_v2_identity_salt_for_backward_compatibility():
    document = GraphicsDocument()
    nodes = _named_nodes(document)
    page = document.active_page
    expected_digest = sha1(
        f"{page.id}|{nodes['name'].id}|named-slot-v2".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:16]

    build_semantic_blocks(document)

    assert list(page.slots) == [f"slot:named:{expected_digest}"]
    assert next(iter(page.slots.values())).metadata["explicit_named_semantics_version"] == 3


def test_saved_v2_named_slot_upgrades_in_place_without_losing_product_state_or_lock():
    document = GraphicsDocument()
    nodes = _named_nodes(document)
    page = document.active_page
    slot = SmartSlot(
        id="slot:named:persisted-v2",
        name="Produto persistido",
        page_id=page.id,
        node_by_role={
            "name": nodes["name"].id,
            "price_complete": nodes["retail"].id,
            "price_currency": nodes["retail_currency"].id,
            "unit": nodes["unit"].id,
        },
        product_id="produto-persistido",
        locked=True,
        metadata={
            "source": "canva-smart-slot",
            "explicit_named_semantics": True,
            "explicit_named_semantics_version": 2,
            "primary_price_node_id": nodes["retail"].id,
            "secondary_price_node_id": "",
            "limit_node_id": "",
            "extra_bindings": {},
            "product_snapshot": {
                "id": "produto-persistido",
                "display_name": "ARROZ PERSISTIDO 5KG",
                "price": "24,90",
            },
        },
    )
    page.slots[slot.id] = slot

    report = build_semantic_blocks(document)

    assert list(page.slots) == ["slot:named:persisted-v2"]
    upgraded = page.slots["slot:named:persisted-v2"]
    assert upgraded.product_id == "produto-persistido"
    assert upgraded.locked is True
    assert upgraded.metadata["product_snapshot"]["display_name"] == "ARROZ PERSISTIDO 5KG"
    assert upgraded.metadata["explicit_named_semantics_version"] == 3
    assert upgraded.node_by_role["quantity"] == nodes["quantity"].id
    assert upgraded.metadata["extra_bindings"]["wholesale_price"] == [nodes["wholesale"].id]
    assert upgraded.metadata["extra_bindings"]["wholesale_price_currency"] == [nodes["wholesale_currency"].id]

    price_blocks = [
        item
        for item in page.metadata["semantic_blocks"].values()
        if item["kind"] == "price_block"
    ]
    assert report.price_blocks == 2
    assert len(price_blocks) == 2
    assert any(item["metadata"].get("commercial_role") == "wholesale" for item in price_blocks)
