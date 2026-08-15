from __future__ import annotations

from dataclasses import dataclass

from srstudio.core.models import Page, ProductCard


@dataclass(frozen=True, slots=True)
class LayerItem:
    card_id: str
    name: str
    z_index: int
    locked: bool
    visible: bool


class LayersManager:
    """Gerencia ordem, bloqueio e visibilidade lógica dos cards da página."""

    def __init__(self, page: Page) -> None:
        self.page = page

    def items(self, product_names: dict[str, str] | None = None) -> tuple[LayerItem, ...]:
        names = product_names or {}
        result: list[LayerItem] = []
        for card in sorted(self.page.cards, key=lambda item: item.z_index, reverse=True):
            result.append(
                LayerItem(
                    card_id=card.id,
                    name=names.get(card.product_id, "Produto"),
                    z_index=card.z_index,
                    locked=card.locked,
                    visible=not bool(card.overrides.get("hidden", False)),
                )
            )
        return tuple(result)

    def _card(self, card_id: str) -> ProductCard | None:
        return next((item for item in self.page.cards if item.id == card_id), None)

    def normalize(self) -> None:
        ordered = sorted(self.page.cards, key=lambda item: item.z_index)
        for index, card in enumerate(ordered):
            card.z_index = index
        self.page.cards[:] = ordered

    def bring_to_front(self, card_id: str) -> None:
        card = self._card(card_id)
        if card is None:
            return
        card.z_index = max((item.z_index for item in self.page.cards), default=0) + 1
        self.normalize()

    def send_to_back(self, card_id: str) -> None:
        card = self._card(card_id)
        if card is None:
            return
        card.z_index = min((item.z_index for item in self.page.cards), default=0) - 1
        self.normalize()

    def move_up(self, card_id: str) -> None:
        self.normalize()
        card = self._card(card_id)
        if card is None:
            return
        target = next((item for item in self.page.cards if item.z_index == card.z_index + 1), None)
        if target is None:
            return
        card.z_index, target.z_index = target.z_index, card.z_index
        self.normalize()

    def move_down(self, card_id: str) -> None:
        self.normalize()
        card = self._card(card_id)
        if card is None:
            return
        target = next((item for item in self.page.cards if item.z_index == card.z_index - 1), None)
        if target is None:
            return
        card.z_index, target.z_index = target.z_index, card.z_index
        self.normalize()

    def set_locked(self, card_id: str, locked: bool) -> None:
        card = self._card(card_id)
        if card is not None:
            card.locked = bool(locked)

    def set_visible(self, card_id: str, visible: bool) -> None:
        card = self._card(card_id)
        if card is not None:
            card.overrides["hidden"] = not bool(visible)
