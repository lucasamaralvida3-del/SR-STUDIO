from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def _grouped_session():
    session = GraphicsSession(GraphicsDocument())
    page = session.page
    a = GraphicsNode(kind=NodeKind.RECT, name="A", transform=Transform(x=100, y=100, width=100, height=80), z_index=10)
    b = GraphicsNode(kind=NodeKind.TEXT, name="B", text="Preço", transform=Transform(x=220, y=160, width=120, height=50), z_index=11)
    page.add_node(a)
    page.add_node(b)
    session.select(a.id)
    session.select(b.id, additive=True)
    group_id = session.group_selected("Produto")
    return session, group_id, a.id, b.id


def test_moving_group_moves_all_descendants_and_undo_restores():
    session, group_id, a_id, b_id = _grouped_session()
    a0 = (session.page.node(a_id).transform.x, session.page.node(a_id).transform.y)
    b0 = (session.page.node(b_id).transform.x, session.page.node(b_id).transform.y)
    session.move_selected(50, 35)
    assert (session.page.node(a_id).transform.x, session.page.node(a_id).transform.y) == (a0[0] + 50, a0[1] + 35)
    assert (session.page.node(b_id).transform.x, session.page.node(b_id).transform.y) == (b0[0] + 50, b0[1] + 35)
    assert session.undo()
    assert session.page.node(group_id) is not None
    assert (session.page.node(a_id).transform.x, session.page.node(a_id).transform.y) == a0


def test_resizing_group_scales_children_from_same_scene_coordinates():
    session, group_id, a_id, b_id = _grouped_session()
    group = session.page.node(group_id)
    old = (group.transform.x, group.transform.y, group.transform.width, group.transform.height)
    session.resize_node(group_id, width=old[2] * 2, height=old[3] * 2)
    a = session.page.node(a_id)
    b = session.page.node(b_id)
    assert a.transform.width == 200
    assert a.transform.height == 160
    assert b.transform.width == 240
    assert b.transform.height == 100
    assert a.transform.x == old[0]
    assert b.transform.x == old[0] + (220 - old[0]) * 2


def test_rotating_group_rotates_descendants_and_preserves_group_relationship():
    session, group_id, a_id, b_id = _grouped_session()
    session.rotate_selected(90)
    group = session.page.node(group_id)
    a = session.page.node(a_id)
    b = session.page.node(b_id)
    assert round(group.transform.rotation) == 90
    assert round(a.transform.rotation) == 90
    assert round(b.transform.rotation) == 90
    assert a.parent_id == group_id
    assert b.parent_id == group_id


def test_hidden_or_locked_group_is_effective_for_children():
    session, group_id, a_id, _ = _grouped_session()
    session.lock_selected(True)
    assert session.effective_locked(group_id)
    assert session.effective_locked(a_id)
    session.lock_selected(False)
    session.hide_selected(True)
    assert not session.effective_visible(group_id)
    assert not session.effective_visible(a_id)


def test_ungroup_keeps_absolute_geometry():
    session, group_id, a_id, b_id = _grouped_session()
    before = {
        a_id: (session.page.node(a_id).transform.x, session.page.node(a_id).transform.y),
        b_id: (session.page.node(b_id).transform.x, session.page.node(b_id).transform.y),
    }
    count = session.ungroup_selected()
    assert count == 1
    assert session.page.node(group_id) is None
    assert session.page.node(a_id).parent_id is None
    assert session.page.node(b_id).parent_id is None
    assert (session.page.node(a_id).transform.x, session.page.node(a_id).transform.y) == before[a_id]
    assert (session.page.node(b_id).transform.x, session.page.node(b_id).transform.y) == before[b_id]
