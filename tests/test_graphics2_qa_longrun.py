from __future__ import annotations

import json

import pytest

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity


def _page(index: int, *, nodes: int = 20) -> GraphicsPage:
    page = GraphicsPage(name=f"QA Página {index + 1}", width=1080, height=1350)
    for node_index in range(nodes):
        column = node_index % 4
        row = node_index // 4
        page.add_node(
            GraphicsNode(
                kind=NodeKind.TEXT if node_index % 2 else NodeKind.RECT,
                name=f"Objeto {index + 1}-{node_index + 1}",
                text=f"QA {index + 1}/{node_index + 1}" if node_index % 2 else "",
                transform=Transform(
                    x=30 + column * 250,
                    y=40 + row * 120,
                    width=210,
                    height=80,
                ),
                style={"font_family": "Arial", "font_size": 20, "fill": "#F5F5F5"},
                z_index=node_index,
            )
        )
    return page


def _document(page_count: int, *, nodes_per_page: int = 20) -> GraphicsDocument:
    pages = [_page(index, nodes=nodes_per_page) for index in range(page_count)]
    document = GraphicsDocument(
        name=f"QA stress {page_count} páginas",
        pages=pages,
        active_page_id=pages[0].id,
    )
    document.metadata["qa_marker"] = {"pages": page_count, "nodes_per_page": nodes_per_page}
    return document


def _canonical(document: GraphicsDocument) -> str:
    return json.dumps(document.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("page_count", [10, 25, 50])
def test_large_documents_roundtrip_without_semantic_drift(tmp_path, page_count):
    document = _document(page_count)
    assert_document_integrity(document)
    expected = _canonical(document)

    path = tmp_path / f"qa-{page_count}.srscene"
    save_package(document, path, embed_local_assets=True)
    reopened = load_package(path, extract_assets_to=tmp_path / f"assets-{page_count}")

    assert_document_integrity(reopened)
    assert _canonical(reopened) == expected
    assert len(reopened.pages) == page_count
    assert sum(len(page.nodes) for page in reopened.pages) == page_count * 20


def test_repeated_25_page_save_load_is_stable_for_20_cycles(tmp_path):
    document = _document(25, nodes_per_page=12)
    expected = _canonical(document)
    current = document

    for cycle in range(20):
        path = tmp_path / f"cycle-{cycle:02d}.srscene"
        save_package(current, path, embed_local_assets=True)
        current = load_package(path, extract_assets_to=tmp_path / f"assets-{cycle:02d}")
        assert_document_integrity(current)
        assert _canonical(current) == expected


def test_undo_redo_move_loop_returns_to_exact_geometry():
    document = _document(1, nodes_per_page=1)
    node_id = next(iter(document.active_page.nodes))
    router = GraphicsCommandRouter(GraphicsSession(document))
    original = router.session.page.node(node_id).transform
    original_xy = (original.x, original.y)

    assert router.dispatch({"name": "select", "node_id": node_id}).ok
    for _ in range(100):
        moved = router.dispatch({"name": "move", "dx": 3.0, "dy": -2.0, "snap": False})
        assert moved.ok and moved.changed
        undone = router.dispatch({"name": "undo"})
        assert undone.ok and undone.changed
        redone = router.dispatch({"name": "redo"})
        assert redone.ok and redone.changed
        undone_again = router.dispatch({"name": "undo"})
        assert undone_again.ok and undone_again.changed

    final = router.session.page.node(node_id).transform
    assert (final.x, final.y) == pytest.approx(original_xy)
    assert_document_integrity(router.session.document)
