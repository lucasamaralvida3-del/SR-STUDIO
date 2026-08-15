from __future__ import annotations

from dataclasses import dataclass

from srstudio.core.models import StudioProject
from srstudio.diagnostics.audit import ProjectAudit
from srstudio.validation.quality import QualityInspector


@dataclass(frozen=True, slots=True)
class Suggestion:
    id: str
    title: str
    detail: str
    action: str
    priority: int
    automatic: bool = False


class SuggestionEngine:
    """Sugestões explicáveis para o botão Otimizar, sem alterar o projeto sozinho."""

    def suggest(self, project: StudioProject) -> list[Suggestion]:
        audit = ProjectAudit().inspect(project)
        quality = QualityInspector().inspect(project)
        suggestions: list[Suggestion] = []
        if audit.missing_images:
            suggestions.append(Suggestion("missing-images", "Completar imagens", f"{audit.missing_images} produto(s) estão sem imagem válida.", "open_missing_images", 100))
        if audit.validation_errors:
            suggestions.append(Suggestion("errors", "Corrigir erros comerciais", f"Existem {audit.validation_errors} erro(s) que podem bloquear a exportação.", "open_validation", 100))
        if audit.orphan_products:
            suggestions.append(Suggestion("orphans", "Revisar produtos não utilizados", f"{audit.orphan_products} produto(s) estão no projeto mas não aparecem em páginas.", "open_orphans", 60))
        for metric in quality.metrics:
            if metric.name == "Layout" and metric.score < 90:
                suggestions.append(Suggestion("layout", "Otimizar distribuição", metric.detail, "auto_layout", 85, True))
            elif metric.name == "Margens" and metric.score < 95:
                suggestions.append(Suggestion("margins", "Corrigir área segura", metric.detail, "fix_safe_area", 80, True))
            elif metric.name == "Consistência" and metric.score < 90:
                suggestions.append(Suggestion("consistency", "Padronizar cards", metric.detail, "normalize_styles", 70, True))
        if audit.quality >= 95 and not audit.validation_errors:
            suggestions.append(Suggestion("ready", "Campanha em excelente estado", f"Qualidade {audit.quality}/100. Faça apenas a prova final antes de exportar.", "proof_mode", 10))
        return sorted(suggestions, key=lambda item: (-item.priority, item.title))
