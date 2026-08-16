from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.semantic_blocks import build_semantic_blocks, semantic_block, semantic_member_ids, semantic_owner


def _text(name: str, role: BindingRole, x: float, y: float, w: float, h: float, text: str) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        transform=Transform(x=x, y=y, width=w, height=h),
        text=text,
        binding_role=role,
        style={"font_family": "Anton", "font_size": 80, "nowrap": True},
    )


def _plain_text(name: str, x: float, y: float, w: float, h: float, text: str) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        transform=Transform(x=x, y=y, width=w, height=h),
        text=text,
        style={"font_family": "Anton", "font_size": 80},
        metadata={"source_name": name},
    )


def test_build_semantic_blocks_preserves_geometry_and_pptx_parentage():
    document = GraphicsDocument(name="Quinta Filé")
    page = document.active_page
    source_group = GraphicsNode(kind=NodeKind.GROUP, name="Grupo PPTX", transform=Transform(x=100, y=200, width=500, height=300))
    page.add_node(source_group)
    currency = _text("R$", BindingRole.CURRENCY, 130, 340, 55, 80, "R$")
    reais = _text("Reais", BindingRole.PRICE_REAIS, 185, 300, 170, 150, "25")
    cents = _text("Centavos", BindingRole.PRICE_CENTS, 350, 305, 65, 65, ",77")
    unit = _text("Unidade", BindingRole.UNIT, 350, 375, 65, 55, "KG")
    name = _text("Nome", BindingRole.NAME, 130, 220, 290, 70, "LINGUIÇA MISTA CASEIRA SR")
    for node in (currency, reais, cents, unit, name):
        page.add_node(node, parent_id=source_group.id)
    slot = SmartSlot(
        id="slot-quinta",
        name="Produto 1",
        page_id=page.id,
        node_by_role={
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: reais.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
            BindingRole.NAME.value: name.id,
        },
        metadata={"source": "canva-smart-slot"},
    )
    page.slots[slot.id] = slot
    before = {node.id: deepcopy(node.transform) for node in (currency, reais, cents, unit, name)}
    parent_before = {node.id: node.parent_id for node in (currency, reais, cents, unit, name)}

    report = build_semantic_blocks(document)

    assert report.price_blocks == 1
    assert report.recovered_price_blocks == 0
    assert report.product_cards == 1
    assert report.incomplete_price_blocks == 0
    price_id = currency.metadata["semantic_price_block_id"]
    card_id = name.metadata["semantic_product_card_id"]
    price = semantic_block(page, price_id)
    card = semantic_block(page, card_id)
    assert price is not None and price["metadata"]["atomic"] is True
    assert price["metadata"]["split_complete"] is True
    assert set(price["roles"]) >= {"currency", "reais", "cents", "unit"}
    assert card is not None and price_id in card["metadata"]["price_blocks"]
    assert set(semantic_member_ids(page, price_id)) == {currency.id, reais.id, cents.id, unit.id}
    assert semantic_owner(page, reais.id) == card_id
    assert semantic_owner(page, reais.id, prefer_card=False) == price_id
    for node in (currency, reais, cents, unit, name):
        assert node.transform == before[node.id]
        assert node.parent_id == parent_before[node.id]
    for node in (currency, reais, cents, unit):
        assert node.style["semantic_fit_policy"] == "overflow_only"
        assert node.style["nowrap"] is True


def test_semantic_blocks_are_idempotent_and_do_not_duplicate_members():
    document = GraphicsDocument()
    page = document.active_page
    currency = _text("R$", BindingRole.CURRENCY, 10, 10, 30, 40, "R$")
    reais = _text("Reais", BindingRole.PRICE_REAIS, 40, 5, 80, 60, "7")
    cents = _text("Centavos", BindingRole.PRICE_CENTS, 118, 8, 30, 25, ",86")
    unit = _text("Unidade", BindingRole.UNIT, 118, 35, 30, 25, "KG")
    for node in (currency, reais, cents, unit):
        page.add_node(node)
    slot = SmartSlot(
        id="slot-1",
        page_id=page.id,
        node_by_role={
            "currency": currency.id,
            "price_reais": reais.id,
            "price_cents": cents.id,
            "unit": unit.id,
        },
        metadata={"extra_bindings": {"price_currency": [currency.id]}},
    )
    page.slots[slot.id] = slot

    first = build_semantic_blocks(document)
    first_blocks = deepcopy(page.metadata["semantic_blocks"])
    second = build_semantic_blocks(document)

    assert first.price_blocks == second.price_blocks == 1
    assert page.metadata["semantic_blocks"] == first_blocks
    block = semantic_block(page, "priceblock:slot-1:price")
    assert block is not None
    assert len(block["members"]) == 4


def test_incomplete_price_block_is_reported_without_destroying_slot():
    document = GraphicsDocument()
    page = document.active_page
    reais = _text("Reais", BindingRole.PRICE_REAIS, 10, 10, 100, 80, "33")
    cents = _text("Centavos", BindingRole.PRICE_CENTS, 100, 10, 40, 30, ",64")
    page.add_node(reais)
    page.add_node(cents)
    slot = SmartSlot(
        id="slot-incompleto",
        page_id=page.id,
        node_by_role={"price_reais": reais.id, "price_cents": cents.id},
    )
    page.slots[slot.id] = slot

    report = build_semantic_blocks(document)

    assert report.price_blocks == 1
    assert report.incomplete_price_blocks == 1
    assert page.slots[slot.id].node_by_role["price_reais"] == reais.id
    block = semantic_block(page, "priceblock:slot-incompleto:price")
    assert block is not None
    assert block["metadata"]["complete"] is False


def test_static_canva_price_is_recovered_from_text_and_geometry_without_smart_slot():
    document = GraphicsDocument(name="Quinta Filé slide 15")
    page = document.active_page
    currency = _plain_text("TextBox 29", 706.0, 1087.0, 53.0, 66.0, "R$")
    reais = _plain_text("TextBox 31", 760.0, 1044.0, 146.0, 160.0, "25")
    cents = _plain_text("TextBox 32", 909.0, 1054.0, 59.0, 56.0, ",77")
    unit = _plain_text("TextBox 30", 917.0, 1128.0, 59.0, 55.0, "KG")
    date = _plain_text("TextBox 26", 92.0, 344.0, 180.0, 12.0, "13/08/2026")
    for node in (currency, reais, cents, unit, date):
        page.add_node(node)
    before = {node.id: deepcopy(node.transform) for node in (currency, reais, cents, unit, date)}

    first = build_semantic_blocks(document)
    first_id = reais.metadata["semantic_price_block_id"]
    first_snapshot = deepcopy(page.metadata["semantic_blocks"])
    second = build_semantic_blocks(document)

    assert first.price_blocks == second.price_blocks == 1
    assert first.recovered_price_blocks == second.recovered_price_blocks == 1
    assert first_id == "priceblock:recovered:textbox-31"
    assert reais.metadata["semantic_price_block_id"] == first_id
    block = semantic_block(page, first_id)
    assert block is not None
    assert block["metadata"]["recovered"] is True
    assert block["metadata"]["source"] == "spatial-recovery"
    assert set(block["roles"]) == {"currency", "reais", "cents", "unit"}
    assert page.metadata["semantic_blocks"] == first_snapshot
    assert "semantic_price_block_id" not in date.metadata
    for node in (currency, reais, cents, unit, date):
        assert node.transform == before[node.id]
