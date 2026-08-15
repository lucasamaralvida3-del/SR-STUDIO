from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from srstudio.core.models import Page, StudioProject


@dataclass(frozen=True, slots=True)
class LearnedSlot:
    x: float
    y: float
    width: float
    height: float
    role: str = "normal"


@dataclass(slots=True)
class LearnedTemplate:
    name: str
    page_width: float
    page_height: float
    background: str
    slots: list[LearnedSlot] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class LayoutLearningEngine:
    """Extrai estrutura geométrica reutilizável sem copiar dados comerciais."""

    def learn_page(self, page: Page, name: str = "Layout aprendido") -> LearnedTemplate:
        slots = [
            LearnedSlot(
                x=card.x / page.width,
                y=card.y / page.height,
                width=card.width / page.width,
                height=card.height / page.height,
                role="hero" if card.highlighted else "normal",
            )
            for card in page.cards
        ]
        areas = [slot.width * slot.height for slot in slots]
        metadata = {
            "card_count": len(slots),
            "hero_count": sum(slot.role == "hero" for slot in slots),
            "average_card_area": mean(areas) if areas else 0.0,
            "source": "learned",
        }
        return LearnedTemplate(name, page.width, page.height, page.background, slots, metadata)

    def learn_project(self, project: StudioProject, prefix: str = "SR") -> list[LearnedTemplate]:
        return [self.learn_page(page, f"{prefix} {page.name}") for page in project.pages]

    def apply(self, template: LearnedTemplate, page: Page) -> int:
        applied = 0
        for card, slot in zip(page.cards, template.slots, strict=False):
            card.x = slot.x * page.width
            card.y = slot.y * page.height
            card.width = slot.width * page.width
            card.height = slot.height * page.height
            card.highlighted = slot.role == "hero"
            applied += 1
        return applied
