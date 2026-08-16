from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession


def _router_with_nodes():
    session = GraphicsSession(GraphicsDocument()); page = session.page
    a = GraphicsNode(kind=NodeKind.RECT, name="A", transform=Transform(x=10, y=10, width=100, height=80)); b = GraphicsNode(kind=NodeKind.RECT, name="B", transform=Transform(x=300, y=10, width=100, height=80)); page.add_node(a); page.add_node(b)
    return GraphicsCommandRouter(session), a, b


def test_router_selection_move_snap_and_undo():
    router, a, _ = _router_with_nodes(); assert router.dispatch({"name": "select", "node_id": a.id}).ok
    result = router.dispatch({"name": "move", "dx": 185, "dy": 0, "zoom": 1.0}); assert result.ok; assert router.session.page.node(a.id).transform.x == 200
    assert router.dispatch({"name": "undo"}).changed; assert router.session.page.node(a.id).transform.x == 10


def test_router_group_ungroup_and_duplicate():
    router, a, b = _router_with_nodes(); router.dispatch({"name": "select", "node_id": a.id}); router.dispatch({"name": "select", "node_id": b.id, "additive": True})
    grouped = router.dispatch({"name": "group"}); assert grouped.changed; group_id = grouped.payload["group_id"]; assert router.session.page.node(group_id).kind is NodeKind.GROUP
    duplicated = router.dispatch({"name": "duplicate"}); assert duplicated.changed; assert duplicated.payload["node_ids"]; assert router.dispatch({"name": "undo"}).changed


def test_router_guides_pages_and_payload_history():
    router, a, _ = _router_with_nodes(); router.dispatch({"name": "select", "node_id": a.id); assert router.dispatch({"name": "add_guide", "axis": "x", "value": 120}).changed; assert 120 in router.session.page.guides_x
    created = router.dispatch({"name": "duplicate_page"}); assert created.changed; assert len(router.session.document.pages) == 2; payload = router.payload(); assert payload["editor"]["can_undo"] is True; assert "selection" in payload["editor"]


def test_router_binds_canva_slot_from_document_product_catalog():
    document = GraphicsDocument(); page = document.active_page
    name = GraphicsNode(kind=NodeKind.TEXT, binding_role=BindingRole.NAME, transform=Transform(width=150, height=30)); whole = GraphicsNode(kind=NodeKind.TEXT, binding_role=BindingRole.PRICE_REAIS, transform=Transform(width=80, height=50)); cents = GraphicsNode(kind=NodeKind.TEXT, binding_role=BindingRole.PRICE_CENTS, transform=Transform(width=50, height=30)); page.add_node(name); page.add_node(whole); page.add_node(cents)
    slot = SmartSlot(id="slot_1", page_id=page.id, node_by_role={BindingRole.NAME.value: name.id, BindingRole.PRICE_REAIS.value: whole.id, BindingRole.PRICE_CENTS.value: cents.id}, metadata={"source": "canva-smart-slot"}); page.slots[slot.id] = slot
    document.metadata["products"] = [{"id": "p1", "display_name": "CAFÉ 500G", "price": "19,98", "unit": "UN"}]
    router = GraphicsCommandRouter(GraphicsSession(document)); result = router.dispatch({"name": "bind_product", "slot_id": "slot_1", "product_id": "p1"}); assert result.changed; assert page.node(name.id).text == "CAFÉ 500G"; assert page.node(whole.id).text == "19"; assert page.node(cents.id).text == ",98"
