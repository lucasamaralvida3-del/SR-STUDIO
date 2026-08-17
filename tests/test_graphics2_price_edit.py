from __future__ import annotations

from copy import deepcopy

import pytest

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.price_edit import edit_price_block
from srstudio.graphics2.semantic_blocks import build_semantic_blocks


def _session():
    document = GraphicsDocument(name="Preço semântico")
    page = document.active_page
    currency = GraphicsNode(kind=NodeKind.TEXT, text="R$", transform=Transform(x=10, y=10, width=30, height=30))
    reais = GraphicsNode(kind=NodeKind.TEXT, text="12", transform=Transform(x=45, y=5, width=80, height=70))
    cents = GraphicsNode(kind=NodeKind.TEXT, text=",99", transform=Transform(x=130, y=10, width=50, height=35))
    unit = GraphicsNode(kind=NodeKind.TEXT, text="/KG", transform=Transform(x=130, y=45, width=50, height=30))
    for node in (currency, reais, cents, unit):
        page.add_node(node)
    slot = SmartSlot(
        name="Produto",
        page_id=page.id,
        node_by_role={
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: reais.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
        },
        product_id="produto-1",
        metadata={"product_snapshot": {"id": "produto-1", "price": "12,99", "unit": "KG"}},
    )
    page.slots[slot.id] = slot
    build_semantic_blocks(document)
    block_id = next(
        block_id
        for block_id, block in page.metadata["semantic_blocks"].items()
        if block.get("kind") == "price_block"
    )
    return GraphicsSession(document), block_id, (currency.id, reais.id, cents.id, unit.id), slot.id


def test_edit_price_block_updates_split_roles_without_moving_template():
    session, block_id, node_ids, slot_id = _session()
    before = {node_id: deepcopy(session.page.node(node_id).transform) for node_id in node_ids}

    assert edit_price_block(session, block_id, "25,77", unit="UN")

    currency, reais, cents, unit = [session.page.node(node_id) for node_id in node_ids]
    assert currency.text == "R$"
    assert reais.text == "25"
    assert cents.text == ",77"
    assert unit.text == "/UN"
    snapshot = session.page.slots[slot_id].metadata["product_snapshot"]
    assert snapshot["price"] == "25,77"
    assert snapshot["unit"] == "UN"
    for node_id in node_ids:
        assert session.page.node(node_id).transform == before[node_id]


def test_edit_price_block_is_one_undoable_transaction():
    session, block_id, node_ids, slot_id = _session()
    original = [session.page.node(node_id).text for node_id in node_ids]
    original_snapshot = deepcopy(session.page.slots[slot_id].metadata["product_snapshot"])

    assert edit_price_block(session, block_id, "9.50", unit="KG")
    assert session.undo()

    assert [session.page.node(node_id).text for node_id in node_ids] == original
    assert session.page.slots[slot_id].metadata["product_snapshot"] == original_snapshot


def test_edit_price_block_rejects_invalid_price_and_locked_member():
    session, block_id, node_ids, _ = _session()
    with pytest.raises(ValueError):
        edit_price_block(session, block_id, "abc")
    session.page.node(node_ids[1]).locked = True
    assert not edit_price_block(session, block_id, "10,00")
