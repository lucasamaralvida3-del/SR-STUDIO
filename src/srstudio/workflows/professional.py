from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from srstudio.core.models import StudioProject
from srstudio.export.service import ExportService
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.products.database import ProductDatabase
from srstudio.products.sync import ProductKnowledgeSync
from srstudio.projects.session import ProjectSession
from srstudio.validation.engine import ValidationEngine
from srstudio.validation.preflight import PreflightInspector
from srstudio.validation.quality import QualityInspector


@dataclass(slots=True)
class WorkflowResult:
    ok: bool
    stage: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


class ProfessionalWorkflow:
    """Orquestra importação, conhecimento local, revisão, preflight, exportação e autosave."""

    def __init__(
        self,
        project: StudioProject,
        session: ProjectSession | None = None,
        product_database: ProductDatabase | None = None,
    ) -> None:
        self.project = project
        self.session = session
        self.importer = UnifiedImportPipeline()
        self.validator = ValidationEngine()
        self.quality = QualityInspector()
        self.preflight = PreflightInspector()
        self.exporter = ExportService()
        self.product_sync = ProductKnowledgeSync(product_database) if product_database is not None else None

    def import_source(self, path: str | Path) -> WorkflowResult:
        summary = self.importer.import_file(path, self.project)
        if self.session:
            self.session.mark_dirty()
        sync_result = self.product_sync.sync_project(self.project) if self.product_sync else None
        issues = self.validator.validate_project(self.project)
        message = f"Importação concluída: {summary.products_added} produto(s), {summary.cards_added} card(s)."
        if sync_result is not None:
            message += f" Banco local atualizado com {sync_result.products} produto(s)."
        return WorkflowResult(
            True,
            "import",
            message,
            {"summary": summary, "issues": issues, "product_sync": sync_result},
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
        return WorkflowResult(
            report.ready,
            "preflight",
            "Projeto pronto para exportação." if report.ready else f"Exportação bloqueada por {report.errors} erro(s).",
            {"report": report},
        )

    def export(self, destination: str | Path, profile_id: str = "print") -> WorkflowResult:
        gate = self.preflight_export()
        if not gate.ok:
            return gate
        if profile_id in {"social", "instagram", "whatsapp"}:
            result = self.exporter.export_social_variants(self.project, destination)
        elif profile_id in {"package", "complete"}:
            result = self.exporter.export_campaign_package(self.project, destination)
        elif profile_id == "pdf":
            result = self.exporter.export_pdf(self.project, destination)
        else:
            scale = 2.0 if profile_id in {"print", "grafica", "high_quality"} else 1.0
            result = self.exporter.export_images(self.project, destination, format_name="PNG", scale=scale)
        if self.session:
            self.session.snapshot("export")
        return WorkflowResult(True, "export", f"Exportação concluída: {len(result.files)} arquivo(s).", {"result": result})

    def autosave(self) -> WorkflowResult:
        if not self.session:
            return WorkflowResult(False, "autosave", "Sessão de projeto não configurada.")
        path = self.session.autosave(force=True)
        return WorkflowResult(
            path is not None,
            "autosave",
            "Autosave concluído." if path else "Autosave não necessário.",
            {"path": path},
        )
