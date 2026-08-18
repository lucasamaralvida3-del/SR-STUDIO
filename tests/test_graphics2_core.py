from __future__ import annotations

import pytest

from srstudio.graphics2 import BindingRole, GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, Transform
from srstudio.graphics2.preflight import run_preflight


def test_scene_round_trip_preserves_semantics():
    document = GraphicsDocument(name="Teste"); page = document.active_page
    node = GraphicsNode(kind=NodeKind.TEXT, text="ARROZ 5KG", binding_role=BindingRole.NAME, transform=Transform(x=10, y=20, width=200, height=50)); page.add_node(node)
    restored = GraphicsDocument.from_dict(document.to_dict()); clone = restored.active_page.nodes[node.id]
    assert clone.kind is NodeKind.TEXT; assert clone.binding_role is BindingRole.NAME; assert clone.transform.x == 10; assert clone.text == "ARROZ 5KG"


def test_history_is_transactional_and_redoable():
    session = GraphicsSession(); node = session.add_text("Produto", x=10, y=20, width=120, height=40); session.select(node.id); session.move_selected(30, 40)
    assert session.page.nodes[node.id].transform.x == 40; assert session.undo(); assert session.page.nodes[node.id].transform.x == 10; assert session.redo(); assert session.page.nodes[node.id].transform.x == 40


def test_product_binding_keeps_price_parts_separate():
    session = GraphicsSession(); page = session.page; fields = {}
    for role in (BindingRole.NAME, BindingRole.CURRENCY, BindingRole.PRICE_REAIS, BindingRole.PRICE_CENTS, BindingRole.UNIT, BindingRole.LIMIT):
        node = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=100, height=30), binding_role=role); page.add_node(node); fields[role] = node.id
    slot = session.create_slot("Produto 1", fields); session.bind_product(slot.id, {"id": "p1", "display_name": "ACÉM BOVINO", "price": "33,64", "unit": "KG", "cpf_limit": "6UN"})
    assert page.nodes[fields[BindingRole.NAME]].text == "ACÉM BOVINO"; assert page.nodes[fields[BindingRole.CURRENCY]].text == "R$"; assert page.nodes[fields[BindingRole.PRICE_REAIS]].text == "33"; assert page.nodes[fields[BindingRole.PRICE_CENTS]].text == ",64"; assert page.nodes[fields[BindingRole.UNIT]].text == "/KG"; assert page.nodes[fields[BindingRole.LIMIT]].text == "LIMITE DE 6UN POR CPF"


def test_product_binding_updates_commercial_fields_and_clears_stale_image():
    session = GraphicsSession(); page = session.page
    roles = (
        BindingRole.NAME,
        BindingRole.RETAIL_PRICE,
        BindingRole.WHOLESALE_PRICE,
        BindingRole.QUANTITY,
        BindingRole.VALIDITY,
    )
    fields = {}
    for role in roles:
        node = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=160, height=32))
        page.add_node(node); fields[role] = node.id
    image = GraphicsNode(kind=NodeKind.IMAGE, transform=Transform(width=180, height=180))
    page.add_node(image); fields[BindingRole.IMAGE] = image.id

    slot = session.create_slot("Atacado", fields)
    assert session.bind_product(slot.id, {
        "id": "p1",
        "display_name": "ARROZ 5KG",
        "price": "24,90",
        "retail_price": "24,90",
        "wholesale_price": "22,50",
        "quantity": "3",
        "validity": "20/08/2026",
        "image_path": "produto-a.png",
    })

    assert page.nodes[fields[BindingRole.RETAIL_PRICE]].text == "R$ 24,90"
    assert page.nodes[fields[BindingRole.WHOLESALE_PRICE]].text == "R$ 22,50"
    assert page.nodes[fields[BindingRole.QUANTITY]].text == "3"
    assert page.nodes[fields[BindingRole.VALIDITY]].text == "20/08/2026"
    assert image.visible is True
    assert image.metadata["bound_image_source"] == "produto-a.png"
    assert image.asset_id in session.document.assets

    assert session.bind_product(slot.id, {
        "id": "p2",
        "display_name": "FEIJÃO 1KG",
        "price": "7,99",
        "retail_price": "7,99",
        "wholesale_price": "6,89",
        "quantity": "6",
        "validity": "21/08/2026",
    })

    assert slot.product_id == "p2"
    assert page.nodes[fields[BindingRole.RETAIL_PRICE]].text == "R$ 7,99"
    assert page.nodes[fields[BindingRole.WHOLESALE_PRICE]].text == "R$ 6,89"
    assert page.nodes[fields[BindingRole.QUANTITY]].text == "6"
    assert image.asset_id == ""
    assert image.visible is False
    assert "bound_image_source" not in image.metadata


def test_rebind_slot_updates_extra_bindings_and_remove_cleans_dangling_refs():
    session = GraphicsSession(); page = session.page
    name = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=200, height=40))
    price = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=140, height=50))
    app_price = GraphicsNode(
        kind=NodeKind.TEXT,
        text="12,34",
        transform=Transform(width=140, height=50),
        metadata={"source": "pptx"},
    )
    for node in (name, price, app_price):
        page.add_node(node)

    slot = session.create_slot("Produto", {BindingRole.NAME: name.id})
    assert session.rebind_slot(
        slot.id,
        {"name": name.id, "retail_price": price.id},
        extra_bindings={"app_price_complete": [app_price.id]},
    )
    assert session.bind_product(slot.id, {
        "id": "p1",
        "display_name": "CAFÉ 500G",
        "price": "19,90",
        "app_price": "17,90",
    })
    assert price.text == "R$ 19,90"
    assert app_price.text == "17,90"

    # The immutable PPTX template token must survive consecutive product swaps.
    assert session.bind_product(slot.id, {
        "id": "p2",
        "display_name": "CAFÉ PREMIUM 500G",
        "price": "21,50",
        "app_price": "18,75",
    })
    assert app_price.text == "18,75"
    assert app_price.metadata["binding_template_text"] == "12,34"

    page.remove_node(app_price.id)
    assert app_price.id not in {
        node_id
        for node_ids in slot.metadata.get("extra_bindings", {}).values()
        for node_id in node_ids
    }

    old_bindings = dict(slot.node_by_role)
    with pytest.raises(KeyError):
        session.rebind_slot(slot.id, {"name": "node-inexistente"})
    assert slot.node_by_role == old_bindings


def test_multiple_product_slots_do_not_share_binding_state():
    session = GraphicsSession(); page = session.page
    name_a = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=180, height=30))
    name_b = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=180, height=30))
    price_a = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=120, height=40))
    price_b = GraphicsNode(kind=NodeKind.TEXT, transform=Transform(width=120, height=40))
    for node in (name_a, name_b, price_a, price_b):
        page.add_node(node)

    slot_a = session.create_slot("A", {BindingRole.NAME: name_a.id, BindingRole.RETAIL_PRICE: price_a.id})
    slot_b = session.create_slot("B", {BindingRole.NAME: name_b.id, BindingRole.RETAIL_PRICE: price_b.id})
    session.bind_product(slot_a.id, {"id": "a", "name": "ARROZ", "price": "20,00"})
    session.bind_product(slot_b.id, {"id": "b", "name": "FEIJÃO", "price": "8,00"})
    session.bind_product(slot_a.id, {"id": "a2", "name": "AÇÚCAR", "price": "18,50"})

    assert slot_a.product_id == "a2"
    assert slot_b.product_id == "b"
    assert name_a.text == "AÇÚCAR"
    assert price_a.text == "R$ 18,50"
    assert name_b.text == "FEIJÃO"
    assert price_b.text == "R$ 8,00"


def test_preflight_detects_missing_asset_without_crashing():
    document = GraphicsDocument(); page = document.active_page; image = GraphicsNode(kind=NodeKind.IMAGE, asset_id="asset_missing", transform=Transform(x=0, y=0, width=100, height=100)); page.add_node(image)
    assert any(issue.code == "MISSING_ASSET" for issue in run_preflight(document))
