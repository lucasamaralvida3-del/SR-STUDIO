from __future__ import annotations

from dataclasses import dataclass

from srstudio.core.models import ProductCard


@dataclass(slots=True)
class Group:
    id: str
    card_ids: list[str]


class GroupEngine:
    """Agrupamento lógico e operações coletivas sem acoplar à interface."""

    def __init__(self) -> None:
        self.groups: dict[str, Group] = {}

    def create(self, group_id: str, cards: list[ProductCard]) -> Group:
        group = Group(group_id, [card.id for card in cards])
        self.groups[group_id] = group
        for card in cards:
            card.overrides["group_id"] = group_id
        return group

    def dissolve(self, group_id: str, cards: list[ProductCard]) -> None:
        self.groups.pop(group_id, None)
        for card in cards:
            if card.overrides.get("group_id") == group_id:
                card.overrides.pop("group_id", None)

    @staticmethod
    def align_left(cards: list[ProductCard]) -> None:
        if not cards:
            return
        x = min(card.x for card in cards)
        for card in cards:
            if not card.locked:
                card.x = x

    @staticmethod
    def align_right(cards: list[ProductCard]) -> None:
        if not cards:
            return
        right = max(card.x + card.width for card in cards)
        for card in cards:
            if not card.locked:
                card.x = right - card.width

    @staticmethod
    def align_top(cards: list[ProductCard]) -> None:
        if not cards:
            return
        y = min(card.y for card in cards)
        for card in cards:
            if not card.locked:
                card.y = y

    @staticmethod
    def align_bottom(cards: list[ProductCard]) -> None:
        if not cards:
            return
        bottom = max(card.y + card.height for card in cards)
        for card in cards:
            if not card.locked:
                card.y = bottom - card.height

    @staticmethod
    def align_center_x(cards: list[ProductCard]) -> None:
        if not cards:
            return
        center = sum(card.x + card.width / 2 for card in cards) / len(cards)
        for card in cards:
            if not card.locked:
                card.x = center - card.width / 2

    @staticmethod
    def align_center_y(cards: list[ProductCard]) -> None:
        if not cards:
            return
        center = sum(card.y + card.height / 2 for card in cards) / len(cards)
        for card in cards:
            if not card.locked:
                card.y = center - card.height / 2

    @staticmethod
    def distribute_horizontal(cards: list[ProductCard]) -> None:
        if len(cards) < 3:
            return
        ordered = sorted(cards, key=lambda card: card.x)
        left = ordered[0].x
        right = ordered[-1].x + ordered[-1].width
        total = sum(card.width for card in ordered)
        gap = max(0.0, (right - left - total) / (len(ordered) - 1))
        cursor = left
        for card in ordered:
            if not card.locked:
                card.x = cursor
            cursor += card.width + gap

    @staticmethod
    def distribute_vertical(cards: list[ProductCard]) -> None:
        if len(cards) < 3:
            return
        ordered = sorted(cards, key=lambda card: card.y)
        top = ordered[0].y
        bottom = ordered[-1].y + ordered[-1].height
        total = sum(card.height for card in ordered)
        gap = max(0.0, (bottom - top - total) / (len(ordered) - 1))
        cursor = top
        for card in ordered:
            if not card.locked:
                card.y = cursor
            cursor += card.height + gap
