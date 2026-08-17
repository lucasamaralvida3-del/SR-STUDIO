from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks


def _router_with_nodes():
    session = GraphicsSession(GraphicsDocument())
    page = session.page
    a = GraphicsNode(kind=NodeKind.RECT, name="A", transform=Transform(x=10, y=10, width=100, height=80))
    b = GraphicsNode(kind=NodeKind.RECT, name="B", transform=Transform(x=300, y=10, width=100, height=80))
    page.add_node(a)
    page.add_node(b)
    return GraphicsCommandRouter(session), a, b


def test_router_selection_move_snap_and_undo():
    router, a, _ = _router_with_nodes()
    assert router.dispatch({"name": "select", "node_id": a.id}).ok
    result = router.dispatch({"name": "move", "dx": 185, "dy": 0, "zoom": 1.0})
    assert result.ok
    assert router.session.page.node(a.id).transform.x == 200
    assert router.dispatch({"name": "undo"}).changed
    assert router.session.page.node(a.id).transform.x == 10


def test_router_group_ungroup_and_duplicate():
    router, a, b = _router_with_nodes()
    router.dispatch({"name": "select", "node_id": a.id})
    router.dispatch({"name": "select", "node_id": b.id, "additive": True})
    grouped = router.dispatch({"name": "group"})
    assert grouped.changed
    group_id = grouped.payload["group_id"]
    assert router.session.page.node(group_id).kind is NodeKind.GROUP
    duplicated = router.dispatch({"name": "duplicate"})
    assert duplicated.changed
    assert duplicated.payload["node_ids"]
    assert router.dispatch({"name": "undo"}).changed


def test_router_guides_pages_and_payload_history():
    router, a, _ = _router_with_nodes()
    router.dispatch({"name": "select", "node_id": a.id})
    assert router.dispatch({"name": "add_guide", "axis": "x", "value": 120}).changed
    assert 120 in router.session.page.guides_x
    created = router.dispatch({"name": "duplicate_page"})
    assert created.changed
    assert len(router.session.document.pages) == 2
    payload = router.payload()
    assert payload["editor"]["can_undo"] is True
    assert "selection" in payload["editor"]


def test_router_binds_canva_slot_from_document_product_catalog():
    document = GraphicsDocument()
    page = document.active_page
    name = GraphicsNode(kind=NodeKind.TEXT, binding_role=BindingRole.NAME, transform=Transform(width=150, height=30))
    whole = GraphicsNode(kind=NodeKind.TEXT, binding_role=BindingRole.PRICE_REAIS, transform=Transform(width=80, height=50))
    cents = GraphicsNode(kind=NodeKind.TEXT, binding_role=BindingRole.PRICE_CENTS, transform=Transform(width=50, height=30))
    page.add_node(name)
    page.add_node(whole)
    page.add_node(cents)
    slot = SmartSlot(
        id="slot_1",
        page_id=page.id,
        node_by_role={
            BindingRole.NAME.value: name.id,
            BindingRole.PRICE_REAIS.value: whole.id,
            BindingRole.PRICE_CENTS.value: cents.id,
        },
        metadata={"source": "canva-smart-slot"},
    )
    page.slots[slot.id] = slot
    document.metadata["products"] = [
        {"id": "p1", "display_name": "CAFÉ 500G", "price": "19,98", "unit": "UN"}
    ]
    router = GraphicsCommandRouter(GraphicsSession(document))
    result = router.dispatch({"name": "bind_product", "slot_id": "slot_1", "product_id": "p1"})
    assert result.changed
    assert page.node(name.id).text == "CAFÉ 500G"
    assert page.node(whole.id).text == "19"
    assert page.node(cents.id).text == ",98"


def test_semantic_selection_keeps_split_price_atomic_when_dragged():
    document = GraphicsDocument(name="Quinta Filé")
    page = document.active_page
    currency = GraphicsNode(kind=NodeKind.TEXT, name="R$", text="R$", transform=Transform(x=100, y=100, width=40, height=50))
    whole = GraphicsNode(kind=NodeKind.TEXT, name="Reais", text="25", transform=Transform(x=140, y=80, width=100, height=90))
    cents = GraphicsNode(kind=NodeKind.TEXT, name="Centavos", text=",77", transform=Transform(x=240, y=85, width=45, height=35))
    unit = GraphicsNode(kind=NodeKind.TEXT, name="Unidade", text="KG", transform=Transform(x=240, y=125, width=45, height=35))
    for node in (currency, whole, cents, unit):
        page.add_node(node)
    slot = SmartSlot(
        id="slot_quinta",
        page_id=page.id,
        node_by_role={
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: whole.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
        },
        metadata={"source": "canva-smart-slot"},
    )
    page.slots[slot.id] = slot
    build_semantic_blocks(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    before = {node.id: (node.transform.x, node.transform.y) for node in (currency, whole, cents, unit)}

    selected = router.dispatch({"name": "select", "node_id": whole.id, "semantic": True})
    assert selected.ok
    assert selected.payload["semantic_kind"] == "price_block"
    assert router.session.selection == {currency.id, whole.id, cents.id, unit.id}
    moved = router.dispatch({"name": "move", "dx": 20, "dy": 15, "snap": False})
    assert moved.changed
    for node in (currency, whole, cents, unit):
        x, y = before[node.id]
        assert page.node(node.id).transform.x == x + 20
        assert page.node(node.id).transform.y == y + 15


def test_exact_selection_still_allows_low_level_editing_of_one_price_token():
    document = GraphicsDocument()
    page = document.active_page
    whole = GraphicsNode(kind=NodeKind.TEXT, text="33", transform=Transform(x=10, y=10, width=80, height=60))
    page.add_node(whole)
    whole.metadata["semantic_price_block_id"] = "priceblock:test"
    page.metadata["semantic_blocks"] = {
        "priceblock:test": {"id": "priceblock:test", "kind": "price_block", "members": [whole.id]}
    }
    router = GraphicsCommandRouter(GraphicsSession(document))

    result = router.dispatch({"name": "select", "node_id": whole.id})

    assert result.ok
    assert result.payload["semantic_block_id"] == ""
    assert router.session.selection == {whole.id}
