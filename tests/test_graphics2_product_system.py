from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2 import (
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    GraphicsSession,
    NodeKind,
    Transform,
    build_semantic_blocks,
    clone_page_with_fresh_ids,
)


def _text(*, text: str = "", source: str = "", width: float = 160, height: float = 40) -> GraphicsNode:
    metadata = {"source": source} if source else {}
    return GraphicsNode(
        kind=NodeKind.TEXT,
        text=text,
        transform=Transform(width=width, height=height),
        metadata=metadata,
    )


def test_optional_product_fields_are_cleared_when_replacement_has_no_values():
    session = GraphicsSession()
    page = session.page
    name = _text()
    limit = _text()
    app_price = _text(text="17,90", source="pptx")
    quantity = _text()
    for node in (name, limit, app_price, quantity):
        page.add_node(node)

    slot = session.create_slot(
        "Produto",
        {
            BindingRole.NAME: name.id,
            BindingRole.LIMIT: limit.id,
            BindingRole.QUANTITY: quantity.id,
        },
    )
    assert session.rebind_slot(
        slot.id,
        slot.node_by_role,
        extra_bindings={"app_price_complete": [app_price.id]},
    )

    assert session.bind_product(
        slot.id,
        {
            "id": "produto-1",
            "display_name": "LEITE 1L",
            "price": "5,99",
            "app_price": "4,99",
            "quantity": "6",
            "cpf_limit": "12UN",
        },
    )
    assert app_price.text == "4,99"
    assert app_price.visible is True
    assert quantity.text == "6"
    assert quantity.visible is True
    assert limit.text == "LIMITE DE 12UN POR CPF"
    assert limit.visible is True

    assert session.bind_product(
        slot.id,
        {
            "id": "produto-2",
            "display_name": "LEITE SEMIDESNATADO 1L",
            "price": "5,49",
        },
    )
    assert app_price.text == ""
    assert app_price.visible is False
    assert quantity.text == ""
    assert quantity.visible is False
    assert limit.text == ""
    assert limit.visible is False


def test_bound_slot_round_trip_preserves_product_snapshot_and_extra_bindings():
    session = GraphicsSession()
    page = session.page
    name = _text()
    retail = _text()
    app_price = _text(text="12,34", source="pptx")
    for node in (name, retail, app_price):
        page.add_node(node)

    slot = session.create_slot("Produto", {BindingRole.NAME: name.id})
    session.rebind_slot(
        slot.id,
        {"name": name.id, "retail_price": retail.id},
        extra_bindings={"app_price_complete": [app_price.id]},
    )
    product = {
        "id": "p-roundtrip",
        "display_name": "CAFÉ 500G",
        "price": "19,90",
        "app_price": "17,90",
        "unit": "UN",
    }
    assert session.bind_product(slot.id, product)

    restored = GraphicsDocument.from_dict(session.document.to_dict())
    restored_page = restored.active_page
    restored_slot = restored_page.slots[slot.id]

    assert restored_slot.product_id == "p-roundtrip"
    assert restored_slot.metadata["product_snapshot"] == product
    assert restored_slot.metadata["extra_bindings"] == {"app_price_complete": [app_price.id]}
    assert restored_page.node(name.id).text == "CAFÉ 500G"
    assert restored_page.node(retail.id).text == "R$ 19,90"
    assert restored_page.node(app_price.id).text == "17,90"
    assert restored_page.node(app_price.id).metadata["binding_template_text"] == "12,34"


def test_duplicate_bound_page_gets_fresh_binding_ids_without_shared_mutable_state():
    session = GraphicsSession()
    page = session.page
    name = _text()
    retail = _text()
    page.add_node(name)
    page.add_node(retail)
    slot = session.create_slot(
        "Produto A",
        {BindingRole.NAME: name.id, BindingRole.RETAIL_PRICE: retail.id},
    )
    session.bind_product(slot.id, {"id": "a", "display_name": "ARROZ 5KG", "price": "24,90"})

    duplicate = clone_page_with_fresh_ids(page)
    assert duplicate.id != page.id
    assert set(duplicate.nodes).isdisjoint(page.nodes)
    assert set(duplicate.slots).isdisjoint(page.slots)

    duplicated_slot = next(iter(duplicate.slots.values()))
    assert duplicated_slot.product_id == "a"
    assert duplicated_slot.metadata["product_snapshot"] == slot.metadata["product_snapshot"]
    duplicated_slot.metadata["product_snapshot"]["display_name"] = "MUTADO"
    assert slot.metadata["product_snapshot"]["display_name"] == "ARROZ 5KG"
    assert duplicated_slot.page_id == duplicate.id
    assert set(duplicated_slot.node_by_role.values()).issubset(duplicate.nodes)


def test_semantic_rebuild_keeps_bound_product_snapshot_after_recovered_slot_update():
    document = GraphicsDocument()
    page = document.active_page
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        text="AÇÚCAR 5KG",
        locked=True,
        transform=Transform(x=100, y=250, width=500, height=80),
        metadata={"source": "pptx"},
    )
    currency = GraphicsNode(
        kind=NodeKind.TEXT,
        text="R$",
        locked=True,
        transform=Transform(x=100, y=500, width=80, height=50),
        metadata={"source": "pptx"},
    )
    price = GraphicsNode(
        kind=NodeKind.TEXT,
        text="18,90",
        locked=True,
        transform=Transform(x=200, y=470, width=420, height=150),
        metadata={"source": "pptx"},
    )
    unit = GraphicsNode(
        kind=NodeKind.TEXT,
        text="CADA",
        locked=True,
        transform=Transform(x=100, y=620, width=120, height=60),
        metadata={"source": "pptx"},
    )
    for node in (name, currency, price, unit):
        page.add_node(node)

    build_semantic_blocks(document)
    session = GraphicsSession(document)
    slot = next(iter(page.slots.values()))
    product = {"id": "acucar-2", "display_name": "AÇÚCAR CRISTAL 5KG", "price": "17,99", "unit": "UN"}
    assert session.bind_product(slot.id, product)

    before_snapshot = deepcopy(slot.metadata["product_snapshot"])
    build_semantic_blocks(document)
    rebuilt_slot = next(iter(page.slots.values()))

    assert rebuilt_slot.product_id == "acucar-2"
    assert rebuilt_slot.metadata["product_snapshot"] == before_snapshot
    assert page.node(name.id).text == "AÇÚCAR CRISTAL 5KG"
    assert page.node(price.id).text == "17,99"
