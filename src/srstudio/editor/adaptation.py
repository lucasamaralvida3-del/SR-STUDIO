from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from srstudio.core.models import Page
from srstudio.editor.layout import LayoutEngine


@dataclass(frozen=True, slots=True)
class TargetFormat:
    id: str
    width: int
    height: int
    label: str


FORMATS = {
    "instagram": TargetFormat("instagram", 1080, 1350, "Instagram 4:5"),
    "whatsapp_status": TargetFormat("whatsapp_status", 1080, 1920, "WhatsApp Status 9:16"),
    "square": TargetFormat("square", 1080, 1080, "Quadrado 1:1"),
    "a4_portrait": TargetFormat("a4_portrait", 2480, 3508, "A4 Retrato 300dpi"),
    "a4_landscape": TargetFormat("a4_landscape", 3508, 2480, "A4 Paisagem 300dpi"),
}


class FormatAdaptationEngine:
    """Cria uma variante reorganizada em vez de simplesmente esticar a arte."""

    def __init__(self, layout: LayoutEngine | None = None) -> None:
        self.layout = layout or LayoutEngine()

    def adapt(self, source: Page, target: TargetFormat | str) -> Page:
        fmt = FORMATS[target] if isinstance(target, str) else target
        page = deepcopy(source)
        page.id = Page().id
        page.name = f"{source.name} — {fmt.label}"
        page.width = float(fmt.width)
        page.height = float(fmt.height)
        # Preserva elementos mestres proporcionalmente.
        sx = page.width / max(source.width, 1)
        sy = page.height / max(source.height, 1)
        for element in page.elements:
            if "x" in element:
                element["x"] = float(element.get("x", 0)) * sx
            if "y" in element:
                element["y"] = float(element.get("y", 0)) * sy
            if "width" in element:
                element["width"] = float(element.get("width", 0)) * sx
            if "height" in element:
                element["height"] = float(element.get("height", 0)) * sy
        highlighted = sum(card.highlighted for card in page.cards)
        plan = self.layout.best(len(page.cards), page.width, page.height, highlighted=highlighted)
        for index, (card, slot) in enumerate(zip(page.cards, plan.slots, strict=False)):
            card.id = f"{page.id}-card-{index+1}"
            card.x = slot.rect.x
            card.y = slot.rect.y
            card.width = slot.rect.width
            card.height = slot.rect.height
            card.highlighted = slot.role == "hero" or (highlighted > 0 and index < highlighted)
        return page

    @staticmethod
    def supported_formats() -> tuple[TargetFormat, ...]:
        return tuple(FORMATS.values())
