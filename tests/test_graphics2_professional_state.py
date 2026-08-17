from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.professional_state import build_professional_editor_state


def test_professional_state_exposes_page_capabilities_and_contextual_inspector():
    document = GraphicsDocument(name="Estado")
    page = document.active_page
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Título",
        text="OFERTA",
        transform=Transform(x=10, y=10, width=100, height=30),
    )
    page.add_node(text)
    document.add_page(GraphicsPage(name="Página 2"))
    document.active_page_id = page.id
    session = GraphicsSession(document)
    session.selection = {text.id}
    session.anchor_id = text.id

    state = build_professional_editor_state(session)
    payload = state.to_dict()

    assert payload["inspector"]["target_type"] == "text"
    assert payload["page"]["count"] == 2
    assert payload["page"]["index"] == 0
    assert payload["page"]["can_delete"] is True
    assert payload["page"]["can_move_previous"] is False
    assert payload["page"]["can_move_next"] is True
    assert payload["usability"]["blockers"] == 0


def test_professional_state_prefers_narrow_priceblock_over_enclosing_productcard():
    document = GraphicsDocument(name="Semântica")
    page = document.active_page
    currency = GraphicsNode(kind=NodeKind.TEXT, text="R$", transform=Transform(x=10, y=10, width=20, height=20))
    reais = GraphicsNode(kind=NodeKind.TEXT, text="9", transform=Transform(x=35, y=10, width=40, height=40))
    image = GraphicsNode(kind=NodeKind.IMAGE, transform=Transform(x=10, y=60, width=100, height=80))
    for node in (currency, reais, image):
        page.add_node(node)
    page.metadata["semantic_blocks"] = {
        "price-1": {
            "id": "price-1",
            "kind": "price_block",
            "name": "Preço",
            "members": [currency.id, reais.id],
        },
        "card-1": {
            "id": "card-1",
            "kind": "product_card",
            "name": "Produto",
            "members": [currency.id, reais.id, image.id],
        },
    }
    session = GraphicsSession(document)
    session.selection = {currency.id, reais.id}
    session.anchor_id = reais.id

    state = build_professional_editor_state(session)

    assert state.semantic_selection_id == "price-1"
    assert state.semantic_selection_kind == "price_block"
    assert state.inspector["target_type"] == "price_block"


def test_professional_state_disables_delete_on_single_page_and_can_require_multi_product():
    document = GraphicsDocument(name="Página única")
    page = document.active_page
    page.add_node(GraphicsNode(kind=NodeKind.TEXT, text="OFERTA"))
    session = GraphicsSession(document)

    state = build_professional_editor_state(session, require_multi_product_page=True)

    assert state.page.count == 1
    assert state.page.can_delete is False
    assert state.usability["professional_usable"] is False
    assert any(issue["code"] == "NO_MULTI_PRODUCT_PAGE" for issue in state.usability["issues"])
