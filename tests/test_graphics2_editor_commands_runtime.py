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
