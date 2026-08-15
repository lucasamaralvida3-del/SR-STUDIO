from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from srstudio.core.models import StudioProject
from srstudio.export.service import CampaignExportService
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.projects.session import ProjectSession
from srstudio.validation.engine import ValidationEngine
from srstudio.validation.preflight import PreflightEngine
from srstudio.validation.quality import QualityInspector


@dataclass(slots=True)
class WorkflowResult:
    ok: bool
    stage: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


class ProfessionalWorkflow:
    """Orquestra o fluxo real sem acoplar a UI aos motores internos."""

    def __init__(self, project: StudioProject, session: ProjectSession | None = None) -> None:
        self.project = project
        self.session = session
        self.importer = UnifiedImportPipeline()
        self.validator = ValidationEngine()
        self.quality = QualityInspector()
        self.preflight = PreflightEngine()
        self.exporter = CampaignExportService()

    def import_source(self, path: str | Path) -> WorkflowResult:
        summary = self.importer.import_file(path, self.project)
        if self.session:
            self.session.mark_dirty()
        issues = self.validator.validate_project(self.project)
        return WorkflowResult(
            True,
            "import",
            f"Importação concluída: {summary.products_added} produto(s), {summary.cards_added} card(s).",
            {"summary": summary, "issues": issues},
        )

    def review(self) -> WorkflowResult:
        issues = self.validator.validate_project(self.project)
        report = self.quality.inspect(self.project)
        summary = self.validator.summary(issues)
        return WorkflowResult(
            summary.get("error", 0) == 0,
            "review",
            f"Revisão concluída: qualidade {report.total}/100, {len(issues)} ocorrência(s).",
            {"issues": issues, "quality": report, "summary": summary},
        )

    def preflight_export(self) -> WorkflowResult:
        report = self.preflight.inspect(self.project)
        blockers = [item for item in report.issues if getattr(item, "severity", "") == "error"]
        return WorkflowResult(
            not blockers,
            "preflight",
            "Projeto pronto para exportação." if not blockers else f"Exportação bloqueada por {len(blockers)} erro(s).",
            {"report": report, "blockers": blockers},
        )

    def export(self, destination: str | Path, profile_id: str = "print") -> WorkflowResult:
        gate = self.preflight_export()
        if not gate.ok:
            return gate
        outputs = self.exporter.export(self.project, destination, profile_id=profile_id)
        if self.session:
            self.session.snapshot("export")
        return WorkflowResult(True, "export", f"Exportação concluída: {len(outputs)} arquivo(s).", {"outputs": outputs})

    def autosave(self) -> WorkflowResult:
        if not self.session:
            return WorkflowResult(False, "autosave", "Sessão de projeto não configurada.")
        path = self.session.autosave(force=True)
        return WorkflowResult(path is not None, "autosave", "Autosave concluído." if path else "Autosave não necessário.", {"path": path})
