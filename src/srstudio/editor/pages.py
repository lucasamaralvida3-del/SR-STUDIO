from __future__ import annotations

from copy import deepcopy

from srstudio.core.models import Page, ProductCard, StudioProject
from srstudio.editor.layout import LayoutEngine


class PageManager:
    def __init__(self, project: StudioProject, layout: LayoutEngine | None = None) -> None:
        self.project = project
        self.layout = layout or LayoutEngine()

    def add_page(self, after: int | None = None, copy_master_from: Page | None = None) -> Page:
        index = len(self.project.pages) if after is None else min(len(self.project.pages), after + 1)
        source = copy_master_from or (self.project.pages[max(0, index - 1)] if self.project.pages else None)
        page = Page(name=f"Página {index + 1}")
        if source is not None:
            page.width = source.width
            page.height = source.height
            page.background = source.background
            page.elements = [deepcopy(item) for item in source.elements if bool(item.get("master", False))]
        self.project.pages.insert(index, page)
        self._rename_pages()
        return page

    def duplicate(self, index: int) -> Page:
        source = self.project.pages[index]
        clone = deepcopy(source)
        clone.id = Page().id
        clone.name = ""
        for card in clone.cards:
            card.id = ProductCard().id
        self.project.pages.insert(index + 1, clone)
        self._rename_pages()
        return clone

    def remove(self, index: int) -> Page | None:
        if len(self.project.pages) <= 1:
            return None
        removed = self.project.pages.pop(index)
        self._rename_pages()
        return removed

    def move(self, old_index: int, new_index: int) -> None:
        page = self.project.pages.pop(old_index)
        self.project.pages.insert(max(0, min(new_index, len(self.project.pages))), page)
        self._rename_pages()

    def distribute_cards(self, cards: list[ProductCard], capacity: int, template_page: Page | None = None) -> list[Page]:
        distribution = self.layout.rebalance(len(cards), capacity)
        if not distribution:
            return []
        while len(self.project.pages) < len(distribution):
            self.add_page(copy_master_from=template_page or self.project.pages[0])
        cursor = 0
        used_pages: list[Page] = []
        for page_index, count in enumerate(distribution):
            page = self.project.pages[page_index]
            page.cards = cards[cursor : cursor + count]
            cursor += count
            used_pages.append(page)
        for page in self.project.pages[len(distribution) :]:
            page.cards = []
        self._rename_pages()
        return used_pages

    def _rename_pages(self) -> None:
        for index, page in enumerate(self.project.pages, start=1):
            page.name = f"Página {index}"
