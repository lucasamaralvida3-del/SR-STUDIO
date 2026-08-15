from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from srstudio.core.models import Page, ProductCard


@dataclass(slots=True)
class SelectionState:
    ids: set[str] = field(default_factory=set)
    anchor_id: str | None = None

    def clear(self) -> None:
        self.ids.clear()
        self.anchor_id = None

    def select(self, card_id: str, additive: bool = False) -> None:
        if not additive:
            self.ids = {card_id}
        else:
            self.ids.add(card_id)
        self.anchor_id = card_id

    def toggle(self, card_id: str) -> None:
        if card_id in self.ids:
            self.ids.remove(card_id)
            if self.anchor_id == card_id:
                self.anchor_id = next(iter(self.ids), None)
        else:
            self.ids.add(card_id)
            self.anchor_id = card_id


class Scene:
    """Modelo de cena independente da UI para o Encartes Studio."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.selection = SelectionState()
        self.clipboard: list[dict[str, Any]] = []

    @property
    def cards(self) -> list[ProductCard]:
        return self.page.cards

    def card(self, card_id: str) -> ProductCard | None:
        return next((item for item in self.cards if item.id == card_id), None)

    def selected(self) -> list[ProductCard]:
        return [card for card in self.cards if card.id in self.selection.ids]

    def add_card(self, card: ProductCard) -> ProductCard:
        if card.z_index == 0 and self.cards:
            card.z_index = max(item.z_index for item in self.cards) + 1
        self.cards.append(card)
        self.selection.select(card.id)
        return card

    def remove_selected(self) -> list[ProductCard]:
        removed = self.selected()
        selected_ids = {item.id for item in removed}
        self.page.cards = [item for item in self.cards if item.id not in selected_ids]
        self.selection.clear()
        return removed

    def move_selected(self, dx: float, dy: float, clamp: bool = True) -> None:
        for card in self.selected():
            if card.locked:
                continue
            x = card.x + dx
            y = card.y + dy
            if clamp:
                x = min(max(0.0, x), max(0.0, self.page.width - card.width))
                y = min(max(0.0, y), max(0.0, self.page.height - card.height))
            card.x, card.y = x, y

    def resize(self, card_id: str, width: float, height: float, min_size: float = 32.0) -> None:
        card = self.card(card_id)
        if card is None or card.locked:
            return
        card.width = min(max(min_size, width), self.page.width - card.x)
        card.height = min(max(min_size, height), self.page.height - card.y)

    def bring_forward(self, card_id: str) -> None:
        card = self.card(card_id)
        if card is None:
            return
        card.z_index = max((item.z_index for item in self.cards), default=0) + 1
        self.cards.sort(key=lambda item: item.z_index)

    def send_backward(self, card_id: str) -> None:
        card = self.card(card_id)
        if card is None:
            return
        card.z_index = min((item.z_index for item in self.cards), default=0) - 1
        self.cards.sort(key=lambda item: item.z_index)

    def lock_selected(self, value: bool = True) -> None:
        for card in self.selected():
            card.locked = value

    def copy_selected(self) -> None:
        self.clipboard = [
            {
                "product_id": card.product_id,
                "x": card.x,
                "y": card.y,
                "width": card.width,
                "height": card.height,
                "rotation": card.rotation,
                "locked": False,
                "highlighted": card.highlighted,
                "style_id": card.style_id,
                "z_index": card.z_index,
                "overrides": dict(card.overrides),
            }
            for card in self.selected()
        ]

    def paste(self, offset: float = 24.0) -> list[ProductCard]:
        pasted: list[ProductCard] = []
        self.selection.clear()
        for data in self.clipboard:
            payload = dict(data)
            payload["x"] = min(max(0.0, float(payload["x"]) + offset), self.page.width - float(payload["width"]))
            payload["y"] = min(max(0.0, float(payload["y"]) + offset), self.page.height - float(payload["height"]))
            payload["z_index"] = max((item.z_index for item in self.cards), default=0) + 1
            card = ProductCard(**payload)
            self.cards.append(card)
            self.selection.ids.add(card.id)
            self.selection.anchor_id = card.id
            pasted.append(card)
        return pasted

    def duplicate_selected(self, offset: float = 24.0) -> list[ProductCard]:
        self.copy_selected()
        return self.paste(offset=offset)
