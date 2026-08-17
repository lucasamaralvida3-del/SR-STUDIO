from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
import srstudio.graphics2.qt_host as qt_host


def _router_with_three_pages() -> GraphicsCommandRouter:
    document = GraphicsDocument(name="Multipágina")
    document.pages[0].name = "Página A"
    document.add_page(GraphicsPage(name="Página B"))
    document.add_page(GraphicsPage(name="Página C"))
    document.active_page_id = document.pages[1].id
    return GraphicsCommandRouter(GraphicsSession(document))


def test_delete_active_page_selects_safe_neighbor_and_roundtrips_with_undo_redo():
    router = _router_with_three_pages()
    original_ids = [page.id for page in router.session.document.pages]
    removed_id = original_ids[1]

    result = router.dispatch({"name": "delete_page", "page_id": removed_id})

    assert result.ok and result.changed
    assert [page.id for page in router.session.document.pages] == [original_ids[0], original_ids[2]]
    assert router.session.document.active_page_id == original_ids[2]
    assert result.payload["active_page_id"] == original_ids[2]

    assert router.dispatch({"name": "undo"}).changed
    assert [page.id for page in router.session.document.pages] == original_ids
    assert router.session.document.active_page_id == removed_id

    assert router.dispatch({"name": "redo"}).changed
    assert [page.id for page in router.session.document.pages] == [original_ids[0], original_ids[2]]
    assert router.session.document.active_page_id == original_ids[2]


def test_delete_inactive_page_keeps_active_page_and_rejects_last_page_deletion():
    router = _router_with_three_pages()
    ids = [page.id for page in router.session.document.pages]
    active_id = router.session.document.active_page_id

    deleted = router.dispatch({"name": "delete_page", "page_id": ids[0]})
    assert deleted.ok and deleted.changed
    assert router.session.document.active_page_id == active_id

    deleted = router.dispatch({"name": "delete_page", "page_id": ids[2]})
    assert deleted.ok and deleted.changed
    assert len(router.session.document.pages) == 1
    only_page = router.session.document.pages[0]
    assert only_page.id == active_id

    rejected = router.dispatch({"name": "delete_page", "page_id": only_page.id})
    assert not rejected.ok
    assert not rejected.changed
    assert len(router.session.document.pages) == 1
    assert router.session.document.active_page_id == active_id


def test_page_inspector_exposes_add_duplicate_delete_and_safe_delete_tooltip():
    source = (Path(qt_host.__file__).with_name("qml") / "PageInspector.qml").read_text(encoding="utf-8")

    assert '"name": "add_page"' in source
    assert '"name": "duplicate_page"' in source
    assert '"name": "delete_page"' in source
    assert "pageCount() > 1" in source
    assert "desfazer disponível" in source
    assert "width: 196" in source
    assert "(196 + pageStrip.spacing)" in source
