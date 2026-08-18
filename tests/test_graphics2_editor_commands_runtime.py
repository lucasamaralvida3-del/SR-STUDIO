from __future__ import annotations

from srstudio.graphics2 import (
    BindingRole,
    GraphicsCommandRouter,
    GraphicsDocument,
    GraphicsNode,
    GraphicsSession,
    NodeKind,
    Transform,
)


def _router_with_three_pages() -> tuple[GraphicsCommandRouter, list[str]]:
    document = GraphicsDocument(name="Multipágina")
    session = GraphicsSession(document)
    first = document.active_page_id
    second = session.add_page(name="Página 2")
    third = session.add_page(name="Página 3")
    return GraphicsCommandRouter(session), [first, second, third]


def test_remove_page_is_transactional_and_selects_adjacent_page():
    router, page_ids = _router_with_three_pages()
    session = router.session
    session.document.active_page_id = page_ids[1]

    result = router.dispatch({"name": "remove_page", "page_id": page_ids[1]})

    assert result.ok
    assert result.changed
    assert [page.id for page in session.document.pages] == [page_ids[0], page_ids[2]]
    assert session.document.active_page_id == page_ids[2]
    assert session.selection == set()

    undo = router.dispatch({"name": "undo"})
    assert undo.ok and undo.changed
    assert [page.id for page in session.document.pages] == page_ids
    assert session.document.active_page_id == page_ids[1]

    redo = router.dispatch({"name": "redo"})
    assert redo.ok and redo.changed
    assert [page.id for page in session.document.pages] == [page_ids[0], page_ids[2]]
    assert session.document.active_page_id == page_ids[2]


def test_remove_page_never_deletes_last_page():
    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    only_page = router.session.document.active_page_id

    result = router.dispatch({"name": "remove_page", "page_id": only_page})

    assert result.ok
    assert not result.changed
    assert len(router.session.document.pages) == 1
    assert router.session.document.active_page_id == only_page


def test_remove_page_rejects_unknown_page_without_mutating_document():
    router, page_ids = _router_with_three_pages()
    before = router.session.document.to_dict()

    result = router.dispatch({"name": "remove_page", "page_id": "page_missing"})

    assert not result.ok
    assert not result.changed
    assert router.session.document.to_dict() == before
    assert [page.id for page in router.session.document.pages] == page_ids


def test_reorder_page_clears_selection_when_it_switches_active_page():
    router, page_ids = _router_with_three_pages()
    session = router.session
    session.document.active_page_id = page_ids[0]
    selected = GraphicsNode(
        kind=NodeKind.RECT,
        name="Selecionado na página antiga",
        transform=Transform(x=10, y=20, width=80, height=60),
    )
    session.page.add_node(selected)
    session.select(selected.id)
    assert session.selection == {selected.id}

    result = router.dispatch(
        {
            "name": "reorder_page",
            "page_id": page_ids[2],
            "target_index": 0,
        }
    )

    assert result.ok and result.changed
    assert session.document.active_page_id == page_ids[2]
    assert session.selection == set()
    assert session.anchor_id is None

    # Undo também precisa voltar à página/ordem anterior sem ressuscitar IDs da
    # seleção pertencente à outra página.
    undo = router.dispatch({"name": "undo"})
    assert undo.ok and undo.changed
    assert session.document.active_page_id == page_ids[0]
    assert session.selection == set()


def test_reorder_page_noop_preserves_selection_when_active_page_does_not_change():
    router, page_ids = _router_with_three_pages()
    session = router.session
    session.document.active_page_id = page_ids[2]
    selected = GraphicsNode(
        kind=NodeKind.RECT,
        transform=Transform(x=10, y=20, width=80, height=60),
    )
    session.page.add_node(selected)
    session.select(selected.id)

    result = router.dispatch(
        {
            "name": "reorder_page",
            "page_id": page_ids[2],
            "target_index": 2,
        }
    )

    assert result.ok and not result.changed
    assert session.selection == {selected.id}
    assert session.anchor_id == selected.id


def test_copy_paste_preserves_group_tree_across_pages_with_fresh_ids_and_undo():
    session = GraphicsSession(GraphicsDocument(name="Clipboard"))
    page = session.page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Grupo",
        transform=Transform(x=100, y=120, width=240, height=180),
        z_index=4,
    )
    child = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Título",
        text="OFERTA",
        transform=Transform(x=120, y=145, width=180, height=50),
        z_index=5,
        style={"font_family": "Arial", "font_size": 31.0},
    )
    page.add_node(group)
    page.add_node(child, parent_id=group.id)
    session.select(group.id)
    router = GraphicsCommandRouter(session)

    copied = router.dispatch({"name": "copy"})
    assert copied.ok and not copied.changed

    router.dispatch({"name": "add_page", "name_value": "Destino"})
    target = session.page
    assert not target.nodes

    pasted = router.dispatch({"name": "paste", "dx": 20, "dy": 30})

    assert pasted.ok and pasted.changed
    assert len(target.roots) == 1
    pasted_group = target.nodes[target.roots[0]]
    assert pasted_group.id != group.id
    assert pasted_group.transform.x == 120
    assert pasted_group.transform.y == 150
    assert len(pasted_group.children) == 1
    pasted_child = target.nodes[pasted_group.children[0]]
    assert pasted_child.id != child.id
    assert pasted_child.parent_id == pasted_group.id
    assert pasted_child.text == "OFERTA"
    assert pasted_child.style == child.style
    assert pasted_child.transform.x == 140
    assert pasted_child.transform.y == 175
    assert session.selection == {pasted_group.id}

    undo = router.dispatch({"name": "undo"})
    assert undo.ok and undo.changed
    assert not session.page.nodes
    assert not session.selection

    redo = router.dispatch({"name": "redo"})
    assert redo.ok and redo.changed
    assert len(session.page.nodes) == 2


def test_cut_keeps_clipboard_after_deleting_original():
    session = GraphicsSession(GraphicsDocument(name="Cut"))
    node = GraphicsNode(
        kind=NodeKind.RECT,
        name="Selo",
        transform=Transform(x=10, y=20, width=90, height=60),
        style={"fill": "#FFFFFF"},
    )
    session.page.add_node(node)
    session.select(node.id)
    router = GraphicsCommandRouter(session)

    cut = router.dispatch({"name": "cut"})
    assert cut.ok and cut.changed
    assert node.id not in session.page.nodes

    pasted = router.dispatch({"name": "paste"})
    assert pasted.ok and pasted.changed
    assert len(session.page.nodes) == 1
    pasted_node = next(iter(session.page.nodes.values()))
    assert pasted_node.id != node.id
    assert pasted_node.name == "Selo"
    assert pasted_node.style == {"fill": "#FFFFFF"}


def test_common_clipboard_refuses_semantic_bound_nodes_instead_of_corrupting_bindings():
    session = GraphicsSession(GraphicsDocument(name="Semantic"))
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Preço",
        text="9,99",
        binding_role=BindingRole.PRICE_REAIS,
        transform=Transform(x=10, y=20, width=100, height=40),
    )
    session.page.add_node(node)
    session.select(node.id)
    router = GraphicsCommandRouter(session)

    result = router.dispatch({"name": "copy"})

    assert not result.ok
    assert not result.changed
    assert "ProductCard/PriceBlock/Smart Slot" in result.message


def test_delete_preserves_locked_nodes_and_deletes_unlocked_selection_only():
    session = GraphicsSession(GraphicsDocument(name="Locks"))
    locked = GraphicsNode(
        kind=NodeKind.RECT,
        name="Protegido",
        locked=True,
        transform=Transform(x=10, y=10, width=100, height=80),
    )
    free = GraphicsNode(
        kind=NodeKind.RECT,
        name="Livre",
        transform=Transform(x=130, y=10, width=100, height=80),
    )
    session.page.add_node(locked)
    session.page.add_node(free)
    session.selection = {locked.id, free.id}
    session.anchor_id = free.id
    router = GraphicsCommandRouter(session)

    result = router.dispatch({"name": "delete"})

    assert result.ok and result.changed
    assert result.payload == {"count": 1, "blocked": 1}
    assert locked.id in session.page.nodes
    assert free.id not in session.page.nodes
    assert session.selection == {locked.id}
    assert session.anchor_id == locked.id


def test_delete_refuses_unlocked_group_when_it_contains_locked_descendant():
    session = GraphicsSession(GraphicsDocument(name="Locked child"))
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Grupo",
        transform=Transform(x=0, y=0, width=200, height=160),
    )
    child = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Texto bloqueado",
        text="NÃO APAGAR",
        locked=True,
        transform=Transform(x=10, y=10, width=180, height=50),
    )
    session.page.add_node(group)
    session.page.add_node(child, parent_id=group.id)
    session.select(group.id)
    router = GraphicsCommandRouter(session)

    result = router.dispatch({"name": "delete"})

    assert result.ok and not result.changed
    assert result.payload == {"count": 0, "blocked": 1}
    assert group.id in session.page.nodes
    assert child.id in session.page.nodes


def test_cut_locked_node_copies_but_never_removes_it():
    session = GraphicsSession(GraphicsDocument(name="Locked cut"))
    node = GraphicsNode(
        kind=NodeKind.RECT,
        name="Trava",
        locked=True,
        transform=Transform(x=10, y=20, width=90, height=60),
    )
    session.page.add_node(node)
    session.select(node.id)
    router = GraphicsCommandRouter(session)

    cut = router.dispatch({"name": "cut"})

    assert cut.ok and not cut.changed
    assert node.id in session.page.nodes
    assert cut.payload == {"count": 0, "blocked": 1}

    # O clipboard continua útil como cópia, mas o original protegido permanece.
    pasted = router.dispatch({"name": "paste", "dx": 25, "dy": 25})
    assert pasted.ok and pasted.changed
    assert len(session.page.nodes) == 2


def test_property_and_layer_commands_preserve_locked_members_in_mixed_selection():
    session = GraphicsSession(GraphicsDocument(name="Mixed locks"))
    locked = GraphicsNode(
        kind=NodeKind.RECT,
        name="Protegido",
        locked=True,
        opacity=0.8,
        z_index=3,
        transform=Transform(x=10, y=10, width=80, height=60),
    )
    free = GraphicsNode(
        kind=NodeKind.RECT,
        name="Livre",
        opacity=0.8,
        z_index=4,
        transform=Transform(x=100, y=10, width=80, height=60),
    )
    session.page.add_node(locked)
    session.page.add_node(free)
    session.selection = {locked.id, free.id}
    session.anchor_id = free.id
    router = GraphicsCommandRouter(session)

    opacity = router.dispatch({"name": "opacity", "value": 0.25})
    assert opacity.ok and opacity.changed
    assert locked.opacity == 0.8
    assert free.opacity == 0.25
    assert session.selection == {locked.id, free.id}

    locked_z = locked.z_index
    layer = router.dispatch({"name": "layer", "mode": "front"})
    assert layer.ok and layer.changed
    assert locked.z_index == locked_z
    assert free.z_index > locked.z_index
    assert session.selection == {locked.id, free.id}


def test_locked_text_and_geometry_commands_report_no_change():
    session = GraphicsSession(GraphicsDocument(name="Locked inspector"))
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Fixado",
        text="ORIGINAL",
        locked=True,
        transform=Transform(x=20, y=30, width=160, height=60),
    )
    session.page.add_node(text)
    session.select(text.id)
    router = GraphicsCommandRouter(session)
    before = session.document.to_dict()

    resized = router.dispatch(
        {
            "name": "resize",
            "node_id": text.id,
            "x": 100,
            "y": 120,
            "width": 400,
            "height": 90,
        }
    )
    edited = router.dispatch({"name": "edit_text", "node_id": text.id, "text": "ALTERADO"})

    assert resized.ok and not resized.changed
    assert edited.ok and not edited.changed
    assert session.document.to_dict() == before


def test_resize_handle_reports_no_change_when_lock_is_inherited_from_group():
    session = GraphicsSession(GraphicsDocument(name="Inherited lock"))
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Grupo bloqueado",
        locked=True,
        transform=Transform(x=0, y=0, width=300, height=220),
    )
    child = GraphicsNode(
        kind=NodeKind.RECT,
        name="Filho",
        transform=Transform(x=20, y=30, width=100, height=80),
    )
    session.page.add_node(group)
    session.page.add_node(child, parent_id=group.id)
    session.select(child.id)
    router = GraphicsCommandRouter(session)
    before = child.transform.to_dict()

    result = router.dispatch(
        {
            "name": "resize_handle",
            "node_id": child.id,
            "handle": "se",
            "dx": 40,
            "dy": 30,
        }
    )

    assert result.ok and not result.changed
    assert session.page.nodes[child.id].transform.to_dict() == before
