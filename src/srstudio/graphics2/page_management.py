from __future__ import annotations

"""Transactional multi-page operations for SR Graphics Engine 2."""

from typing import TYPE_CHECKING

from .page_clone import clone_page_with_fresh_ids

if TYPE_CHECKING:
    from .operations import GraphicsSession


def rename_page(session: "GraphicsSession", page_id: str, name: str) -> bool:
    """Rename a page through history so undo/redo remains authoritative."""
    page = session.document.page(str(page_id))
    cleaned = str(name or "").strip()
    if page is None or not cleaned or page.name == cleaned:
        return False
    with session.transaction("Renomear página"):
        page.name = cleaned
    return True


def delete_page(session: "GraphicsSession", page_id: str) -> bool:
    """Delete one page while guaranteeing that a document always keeps a page."""
    document = session.document
    if len(document.pages) <= 1:
        return False
    index = next((i for i, page in enumerate(document.pages) if page.id == page_id), -1)
    if index < 0:
        return False
    with session.transaction("Excluir página"):
        removed = document.pages.pop(index)
        if document.active_page_id == removed.id:
            next_index = min(index, len(document.pages) - 1)
            document.active_page_id = document.pages[next_index].id
    session.clear_selection()
    return True


def duplicate_page(session: "GraphicsSession", page_id: str | None = None, *, name: str | None = None) -> str:
    """Duplicate any page with fresh ids and activate the new copy."""
    source = session.document.page(str(page_id or session.document.active_page_id))
    if source is None:
        return ""
    with session.transaction("Duplicar página"):
        page = clone_page_with_fresh_ids(source, name=name)
        source_index = next(index for index, item in enumerate(session.document.pages) if item.id == source.id)
        session.document.pages.insert(source_index + 1, page)
        session.document.active_page_id = page.id
    session.clear_selection()
    return page.id


def reorder_page(session: "GraphicsSession", page_id: str, target_index: int) -> bool:
    """Move a page to a bounded target index transactionally."""
    pages = session.document.pages
    if len(pages) < 2:
        return False
    current_index = next((index for index, page in enumerate(pages) if page.id == page_id), -1)
    if current_index < 0:
        return False
    target_index = max(0, min(len(pages) - 1, int(target_index)))
    if target_index == current_index:
        return False
    with session.transaction("Reordenar página"):
        page = pages.pop(current_index)
        pages.insert(target_index, page)
        session.document.active_page_id = page.id
    session.clear_selection()
    return True
