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

    def resize_from_handle(
        self,
        card_id: str,
        handle: str,
        x: float,
        y: float,
        min_size: float = 32.0,
    ) -> None:
        """Redimensiona um card por qualquer uma das oito alças."""
        card = self.card(card_id)
        if card is None or card.locked:
            return
        left, top = card.x, card.y
        right, bottom = card.x + card.width, card.y + card.height

        if "w" in handle:
            left = min(max(0.0, x), right - min_size)
        if "e" in handle:
            right = max(min(self.page.width, x), left + min_size)
        if "n" in handle:
            top = min(max(0.0, y), bottom - min_size)
        if "s" in handle:
            bottom = max(min(self.page.height, y), top + min_size)

        card.x = left
        card.y = top
        card.width = right - left
        card.height = bottom - top

    def rotate(self, card_id: str, angle: float, snap: float | None = 15.0) -> None:
        card = self.card(card_id)
        if card is None or card.locked:
            return
        value = float(angle) % 360.0
        if snap and snap > 0:
            value = round(value / snap) * snap
        card.rotation = value % 360.0

    def rotate_selected(self, delta: float, snap: float | None = 15.0) -> None:
        for card in self.selected():
            if not card.locked:
                self.rotate(card.id, card.rotation + delta, snap=snap)

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

    def bring_selected_to_front(self) -> None:
        selected = self.selected()
        if not selected:
            return
        start = max((item.z_index for item in self.cards), default=0) + 1
        for offset, card in enumerate(selected):
            card.z_index = start + offset
        self.cards.sort(key=lambda item: item.z_index)

    def send_selected_to_back(self) -> None:
        selected = self.selected()
        if not selected:
            return
        start = min((item.z_index for item in self.cards), default=0) - len(selected)
        for offset, card in enumerate(selected):
            card.z_index = start + offset
        self.cards.sort(key=lambda item: item.z_index)

    def lock_selected(self, value: bool = True) -> None:
        for card in self.selected():
            card.locked = value

    def hide_selected(self, value: bool = True) -> None:
        for card in self.selected():
            card.overrides["hidden"] = bool(value)

    def align_selected(self, mode: str) -> None:
        cards = [card for card in self.selected() if not card.locked]
        if len(cards) < 2:
            return
        left = min(card.x for card in cards)
        right = max(card.x + card.width for card in cards)
        top = min(card.y for card in cards)
        bottom = max(card.y + card.height for card in cards)
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2

        for card in cards:
            if mode == "left":
                card.x = left
            elif mode == "center_x":
                card.x = center_x - card.width / 2
            elif mode == "right":
                card.x = right - card.width
            elif mode == "top":
                card.y = top
            elif mode == "center_y":
                card.y = center_y - card.height / 2
            elif mode == "bottom":
                card.y = bottom - card.height

    def distribute_selected(self, axis: str) -> None:
        cards = [card for card in self.selected() if not card.locked]
        if len(cards) < 3:
            return
        if axis == "horizontal":
            cards.sort(key=lambda item: item.x)
            start = cards[0].x
            end = cards[-1].x + cards[-1].width
            content = sum(card.width for card in cards)
            gap = max(0.0, (end - start - content) / (len(cards) - 1))
            cursor = start
            for card in cards:
                card.x = cursor
                cursor += card.width + gap
        elif axis == "vertical":
            cards.sort(key=lambda item: item.y)
            start = cards[0].y
            end = cards[-1].y + cards[-1].height
            content = sum(card.height for card in cards)
            gap = max(0.0, (end - start - content) / (len(cards) - 1))
            cursor = start
            for card in cards:
                card.y = cursor
                cursor += card.height + gap

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
