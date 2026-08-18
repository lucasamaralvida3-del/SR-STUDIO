from __future__ import annotations

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsDocument, GraphicsSession


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
