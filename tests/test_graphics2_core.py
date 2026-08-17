from __future__ import annotations

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


def test_preflight_detects_missing_asset_without_crashing():
    document = GraphicsDocument(); page = document.active_page; image = GraphicsNode(kind=NodeKind.IMAGE, asset_id="asset_missing", transform=Transform(x=0, y=0, width=100, height=100)); page.add_node(image)
    assert any(issue.code == "MISSING_ASSET" for issue in run_preflight(document))
