from __future__ import annotations

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.page_clone import clone_page_with_fresh_ids, duplicate_active_page
from srstudio.graphics2.semantic_blocks import build_semantic_blocks


def _fixture():
    document = GraphicsDocument(name="Encartes multipágina")
    page = document.active_page

    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Produto",
        transform=Transform(x=40, y=60, width=420, height=320),
    )
    page.add_node(group)
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        text="ACÉM BOVINO",
        transform=Transform(x=60, y=70, width=260, height=45),
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem",
        asset_id="asset_shared",
        transform=Transform(x=70, y=130, width=220, height=150),
    )
    reais = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Reais",
        text="33",
        transform=Transform(x=300, y=220, width=90, height=90),
    )
    cents = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Centavos",
        text=",64",
        transform=Transform(x=390, y=225, width=55, height=45),
    )
    unit = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Unidade",
        text="/KG",
        transform=Transform(x=390, y=275, width=55, height=35),
    )
    currency = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Moeda",
        text="R$",
        transform=Transform(x=260, y=240, width=40, height=40),
    )
    for node in (name, image, currency, reais, cents, unit):
        page.add_node(node, parent_id=group.id)

    slot = SmartSlot(
        name="Produto 1",
        page_id=page.id,
        node_by_role={
            BindingRole.NAME.value: name.id,
            BindingRole.IMAGE.value: image.id,
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: reais.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
        },
        product_id="produto-1",
        metadata={"product_snapshot": {"id": "produto-1", "price": "33,64", "unit": "KG"}},
    )
    page.slots[slot.id] = slot
    build_semantic_blocks(document)
    return document, slot.id


def test_clone_page_generates_independent_page_node_and_slot_ids():
    document, source_slot_id = _fixture()
    source = document.active_page
    clone = clone_page_with_fresh_ids(source)

    assert clone.id != source.id
    assert clone.name == f"{source.name} - cópia"
    assert set(clone.nodes).isdisjoint(source.nodes)
    assert set(clone.slots).isdisjoint(source.slots)
    assert source_slot_id not in clone.slots

    assert len(clone.nodes) == len(source.nodes)
    assert len(clone.slots) == len(source.slots)
    assert {node.asset_id for node in clone.nodes.values() if node.asset_id} == {"asset_shared"}

    for slot in clone.slots.values():
        assert slot.page_id == clone.id
        assert set(slot.node_by_role.values()).issubset(clone.nodes)
        assert slot.product_id == "produto-1"


def test_clone_page_rebuilds_semantic_blocks_against_clone_only():
    document, _ = _fixture()
    source = document.active_page
    source_block_ids = set((source.metadata.get("semantic_blocks") or {}).keys())

    clone = clone_page_with_fresh_ids(source)
    clone_blocks = clone.metadata.get("semantic_blocks") or {}

    assert clone_blocks
    assert set(clone_blocks).isdisjoint(source_block_ids)
    for block in clone_blocks.values():
        assert set(block.get("members") or []).issubset(clone.nodes)
        assert block.get("slot_id") in clone.slots


def test_duplicate_active_page_is_transactional_and_undo_restores_one_page():
    document, _ = _fixture()
    session = GraphicsSession(document)
    original_page_id = session.page.id

    copied_page_id = duplicate_active_page(session, name="Página 2")

    assert copied_page_id != original_page_id
    assert len(session.document.pages) == 2
    assert session.document.active_page_id == copied_page_id
    assert session.document.pages[1].name == "Página 2"

    assert session.undo()
    assert len(session.document.pages) == 1
    assert session.document.active_page_id == original_page_id

    assert session.redo()
    assert len(session.document.pages) == 2
    assert session.document.active_page_id == copied_page_id
