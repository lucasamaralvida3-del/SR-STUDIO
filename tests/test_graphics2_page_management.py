from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.page_management import delete_page, duplicate_page, rename_page, reorder_page


def _session() -> GraphicsSession:
    document = GraphicsDocument(name="Multipage")
    document.pages[0].name = "Página 1"
    document.pages[0].add_node(GraphicsNode(kind=NodeKind.TEXT, text="Oferta"))
    document.add_page(GraphicsPage(name="Página 2"))
    document.active_page_id = document.pages[0].id
    return GraphicsSession(document)


def test_rename_page_participates_in_undo_redo():
    session = _session()
    page_id = session.page.id
    assert rename_page(session, page_id, "Carnes")
    assert session.page.name == "Carnes"
    assert session.undo()
    assert session.page.name == "Página 1"
    assert session.redo()
    assert session.page.name == "Carnes"


def test_delete_active_page_selects_neighbor_and_can_be_undone():
    session = _session()
    first_id = session.document.pages[0].id
    second_id = session.document.pages[1].id
    session.document.active_page_id = first_id
    assert delete_page(session, first_id)
    assert len(session.document.pages) == 1
    assert session.document.active_page_id == second_id
    assert session.undo()
    assert len(session.document.pages) == 2
    assert session.document.active_page_id == first_id


def test_delete_page_refuses_to_remove_last_page():
    document = GraphicsDocument(name="Uma página")
    session = GraphicsSession(document)
    assert not delete_page(session, session.page.id)
    assert len(session.document.pages) == 1


def test_duplicate_page_inserts_copy_after_source_with_independent_ids():
    session = _session()
    source = session.document.pages[0]
    source_node_ids = set(source.nodes)
    copied_id = duplicate_page(session, source.id, name="Página 1B")
    assert copied_id
    assert [page.name for page in session.document.pages] == ["Página 1", "Página 1B", "Página 2"]
    copied = session.document.page(copied_id)
    assert copied is not None
    assert set(copied.nodes).isdisjoint(source_node_ids)
    assert session.document.active_page_id == copied_id


def test_reorder_page_is_bounded_and_undoable():
    session = _session()
    first_id = session.document.pages[0].id
    assert reorder_page(session, first_id, 99)
    assert session.document.pages[-1].id == first_id
    assert session.undo()
    assert session.document.pages[0].id == first_id
