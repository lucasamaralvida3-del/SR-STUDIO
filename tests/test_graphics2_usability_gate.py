from __future__ import annotations

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.semantic_blocks import build_semantic_blocks
from srstudio.graphics2.usability_gate import inspect_encarte_usability


def _realistic_encarte_document() -> GraphicsDocument:
    document = GraphicsDocument(name="Quinta Filé")
    page = document.active_page

    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=50, y=220, width=280, height=260),
        binding_role=BindingRole.IMAGE,
    )
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        text="ACÉM BOVINO",
        transform=Transform(x=50, y=490, width=280, height=60),
        binding_role=BindingRole.NAME,
    )
    currency = GraphicsNode(
        kind=NodeKind.TEXT,
        text="R$",
        transform=Transform(x=50, y=570, width=50, height=50),
        binding_role=BindingRole.CURRENCY,
    )
    reais = GraphicsNode(
        kind=NodeKind.TEXT,
        text="33",
        transform=Transform(x=100, y=550, width=100, height=80),
        binding_role=BindingRole.PRICE_REAIS,
    )
    cents = GraphicsNode(
        kind=NodeKind.TEXT,
        text=",64",
        transform=Transform(x=200, y=555, width=80, height=45),
        binding_role=BindingRole.PRICE_CENTS,
    )
    unit = GraphicsNode(
        kind=NodeKind.TEXT,
        text="/KG",
        transform=Transform(x=205, y=600, width=80, height=35),
        binding_role=BindingRole.UNIT,
    )
    for node in (image, name, currency, reais, cents, unit):
        page.add_node(node)

    slot = SmartSlot(
        name="Produto 1",
        page_id=page.id,
        node_by_role={
            BindingRole.IMAGE.value: image.id,
            BindingRole.NAME.value: name.id,
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: reais.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
        },
        product_id="produto-1",
    )
    page.slots[slot.id] = slot
    build_semantic_blocks(document)
    return document


def test_blank_document_is_not_professional_usable():
    report = inspect_encarte_usability(GraphicsDocument())

    assert report.ready is False
    assert report.blockers > 0
    failed = {item.code for item in report.checks if not item.passed}
    assert "VISIBLE_CONTENT" in failed
    assert "PRODUCT_CARD_AVAILABLE" in failed


def test_semantic_product_page_passes_document_usability_gate():
    document = _realistic_encarte_document()

    report = inspect_encarte_usability(document, require_bound_product=True)

    assert report.ready is True
    assert report.blockers == 0
    assert report.metrics["product_cards"] == 1
    assert report.metrics["price_blocks"] == 1
    assert report.metrics["smart_slots"] == 1
    assert report.metrics["bound_slots"] == 1


def test_gate_rejects_slot_owned_by_another_page():
    document = _realistic_encarte_document()
    page = document.active_page
    next(iter(page.slots.values())).page_id = "page_wrong"

    report = inspect_encarte_usability(document)

    assert report.ready is False
    failed = {item.code for item in report.checks if not item.passed}
    assert "SLOT_PAGE_OWNERSHIP" in failed


def test_gate_rejects_orphan_semantic_member():
    document = _realistic_encarte_document()
    page = document.active_page
    block = next(iter(page.metadata["semantic_blocks"].values()))
    block["members"].append("node_missing")

    report = inspect_encarte_usability(document)

    assert report.ready is False
    assert report.metrics["semantic_missing_members"] == 1


def test_gate_detects_duplicate_page_ids_even_when_page_content_is_valid():
    document = _realistic_encarte_document()
    duplicate = GraphicsDocument.from_dict(document.to_dict()).active_page
    duplicate.name = "Página duplicada"
    document.pages.append(duplicate)

    report = inspect_encarte_usability(document)

    assert report.ready is False
    assert report.metrics["duplicate_page_ids"] == 1
    failed = {item.code for item in report.checks if not item.passed}
    assert "UNIQUE_PAGE_IDS" in failed
