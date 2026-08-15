from __future__ import annotations

from dataclasses import dataclass

from srstudio.core.models import StudioProject
from srstudio.editor.layout import Rect


@dataclass(frozen=True, slots=True)
class QualityMetric:
    name: str
    score: int
    detail: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    total: int
    metrics: tuple[QualityMetric, ...]


class QualityInspector:
    """Mede consistência visual com regras determinísticas e explicáveis."""

    def inspect(self, project: StudioProject) -> QualityReport:
        metrics = (
            self._layout(project),
            self._images(project),
            self._commercial_data(project),
            self._margins(project),
            self._consistency(project),
        )
        total = round(sum(item.score for item in metrics) / len(metrics)) if metrics else 100
        return QualityReport(total=total, metrics=metrics)

    def _layout(self, project: StudioProject) -> QualityMetric:
        collisions = 0
        count = 0
        for page in project.pages:
            rects = [Rect(card.x, card.y, card.width, card.height) for card in page.cards]
            count += len(rects)
            for index, first in enumerate(rects):
                for second in rects[index + 1 :]:
                    collisions += int(first.intersects(second))
        penalty = min(80, collisions * 15)
        return QualityMetric("Layout", max(20, 100 - penalty), f"{collisions} colisões em {count} cards")

    def _images(self, project: StudioProject) -> QualityMetric:
        if not project.products:
            return QualityMetric("Imagens", 100, "Sem produtos")
        missing = sum(not item.has_image for item in project.products)
        ratio = missing / len(project.products)
        return QualityMetric("Imagens", max(0, round(100 - ratio * 100)), f"{missing} produto(s) sem imagem")

    def _commercial_data(self, project: StudioProject) -> QualityMetric:
        if not project.products:
            return QualityMetric("Dados", 100, "Sem produtos")
        problems = sum(not item.name or item.price is None or not item.unit for item in project.products)
        ratio = problems / len(project.products)
        return QualityMetric("Dados", max(0, round(100 - ratio * 100)), f"{problems} produto(s) incompletos")

    def _margins(self, project: StudioProject, safe_margin: float = 20.0) -> QualityMetric:
        outside = 0
        total = 0
        for page in project.pages:
            for card in page.cards:
                total += 1
                if (
                    card.x < safe_margin
                    or card.y < safe_margin
                    or card.x + card.width > page.width - safe_margin
                    or card.y + card.height > page.height - safe_margin
                ):
                    outside += 1
        score = 100 if total == 0 else max(0, round(100 - outside / total * 100))
        return QualityMetric("Margens", score, f"{outside} card(s) fora da área segura")

    def _consistency(self, project: StudioProject) -> QualityMetric:
        styles = [card.style_id for page in project.pages for card in page.cards if not card.highlighted]
        if not styles:
            return QualityMetric("Consistência", 100, "Sem cards normais")
        dominant = max(set(styles), key=styles.count)
        different = sum(item != dominant for item in styles)
        score = max(0, round(100 - different / len(styles) * 100))
        return QualityMetric("Consistência", score, f"{different} card(s) fora do estilo dominante")
