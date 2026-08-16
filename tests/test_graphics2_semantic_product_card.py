from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks, semantic_block


def _locked_text(name: str, text: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": 40},
        metadata={"source_name": name},
    )


def test_recovered_price_promotes_real_pptx_group_to_atomic_product_card():
    document = GraphicsDocument(name="Quinta Filé card")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group 42",
        locked=False,
        transform=Transform(x=100, y=100, width=420, height=330),
        metadata={
            "source": "pptx-group",
            "source_name": "Group 42",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    name = _locked_text("TextBox Name", "LINGUIÇA MISTA CASEIRA SR", 145, 125, 300, 55)
    currency = _locked_text("TextBox 29", "R$", 255, 300, 45, 55)
    whole = _locked_text("TextBox 31", "25", 300, 260, 125, 120)
    cents = _locked_text("TextBox 32", ",77", 425, 270, 48, 45)
    unit = _locked_text("TextBox 30", "KG", 425, 330, 48, 42)
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Picture 1",
        locked=True,
        transform=Transform(x=135, y=180, width=230, height=170),
        metadata={"source_name": "Picture 1"},
    )
    for node in (name, image, currency, whole, cents, unit):
        page.add_node(node, parent_id=group.id)

    report = build_semantic_blocks(document)

    assert report.recovered_price_blocks == 1
    assert report.recovered_product_cards == 1
    price_id = whole.metadata["semantic_price_block_id"]
    card_id = whole.metadata["semantic_product_card_id"]
    price = semantic_block(page, price_id)
    card = semantic_block(page, card_id)
    assert price is not None and price["metadata"]["recovered"] is True
    assert card is not None and card["metadata"]["recovered"] is True
    assert card["metadata"]["source"] == "pptx-group-recovery"
    assert card["members"] == [group.id]
    assert set(card["metadata"]["content_members"]) == {name.id, image.id, currency.id, whole.id, cents.id, unit.id}
    assert group.metadata["semantic_product_card_id"] == card_id
    assert name.metadata["semantic_product_card_id"] == card_id


def test_explicit_card_selection_moves_the_whole_recovered_pptx_group():
    document = GraphicsDocument(name="Quinta Filé group move")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group Card",
        transform=Transform(x=50, y=50, width=350, height=280),
        metadata={
            "source": "pptx-group",
            "source_name": "Group Card",
            "pptx_group_generated": True,
            "pptx_group_depth": 2,
        },
    )
    page.add_node(group)
    name = _locked_text("Name", "ACÉM BOVINO", 80, 70, 180, 45)
    currency = _locked_text("Currency", "R$", 150, 220, 40, 50)
    whole = _locked_text("Whole", "33", 190, 190, 100, 100)
    cents = _locked_text("Cents", ",64", 290, 195, 45, 40)
    unit = _locked_text("Unit", "KG", 290, 245, 45, 40)
    for node in (name, currency, whole, cents, unit):
        page.add_node(node, parent_id=group.id)
    build_semantic_blocks(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    before = {node.id: (node.transform.x, node.transform.y) for node in (group, name, currency, whole, cents, unit)}

    selected = router.dispatch(
        {"name": "select", "node_id": whole.id, "semantic": True, "semantic_scope": "card"}
    )
    assert selected.ok
    assert selected.payload["semantic_kind"] == "product_card"
    assert router.session.selection == {group.id}
    moved = router.dispatch({"name": "move", "dx": 25, "dy": 10, "snap": False})
    assert moved.changed
    for node in (group, name, currency, whole, cents, unit):
        x, y = before[node.id]
        assert page.node(node.id).transform.x == x + 25
        assert page.node(node.id).transform.y == y + 10
