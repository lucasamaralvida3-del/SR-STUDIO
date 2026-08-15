from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from srstudio.core.models import StudioProject
from srstudio.editor.adaptation import FormatAdaptationEngine
from srstudio.export.renderer import FlyerRenderer


@dataclass(slots=True)
class ExportResult:
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExportService:
    """Exportação centralizada de campanhas para impressão e canais digitais."""

    def __init__(self) -> None:
        self.renderer = FlyerRenderer()
        self.adaptation = FormatAdaptationEngine()

    def export_images(
        self,
        project: StudioProject,
        output_dir: str | Path,
        *,
        format_name: str = "PNG",
        scale: float = 1.0,
    ) -> ExportResult:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        result = ExportResult()
        extension = ".png" if format_name.upper() == "PNG" else ".jpg"
        for index, page in enumerate(project.pages, start=1):
            image = self.renderer.render_page(project, page, scale=scale)
            path = target / f"{self._safe(project.name)}_pagina_{index:02d}{extension}"
            if extension == ".jpg":
                image.convert("RGB").save(path, "JPEG", quality=95, optimize=True)
            else:
                image.save(path, "PNG", optimize=True)
            result.files.append(path)
        return result

    def export_pdf(
        self,
        project: StudioProject,
        output_path: str | Path,
        *,
        scale: float = 2.0,
        dpi: int = 300,
    ) -> ExportResult:
        """Gera PDF multipágina usando o mesmo renderizador do preview."""
        target = Path(output_path)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        target.parent.mkdir(parents=True, exist_ok=True)
        pages = [self.renderer.render_page(project, page, scale=scale).convert("RGB") for page in project.pages]
        result = ExportResult()
        if not pages:
            result.warnings.append("O projeto não possui páginas para exportar.")
            return result
        first, remaining = pages[0], pages[1:]
        first.save(target, "PDF", resolution=float(dpi), save_all=True, append_images=remaining)
        result.files.append(target)
        return result

    def export_social_variants(self, project: StudioProject, output_dir: str | Path) -> ExportResult:
        """Cria variantes reorganizadas, não simples canvases esticados."""
        target = Path(output_dir)
        result = ExportResult()
        original = self.export_images(project, target / "original", format_name="PNG", scale=1.0)
        result.files.extend(original.files)
        for format_id in ("instagram", "whatsapp_status", "square"):
            variant = deepcopy(project)
            variant.pages = [self.adaptation.adapt(page, format_id) for page in project.pages]
            rendered = self.export_images(variant, target / format_id, format_name="PNG", scale=1.0)
            result.files.extend(rendered.files)
            result.warnings.extend(rendered.warnings)
        return result

    def export_campaign_package(self, project: StudioProject, output_dir: str | Path) -> ExportResult:
        """Entrega completa: PDF impressão + PNG alta + formatos sociais."""
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        result = ExportResult()
        pdf = self.export_pdf(project, target / f"{self._safe(project.name)}_IMPRESSAO.pdf", scale=2.0, dpi=300)
        images = self.export_images(project, target / "alta_qualidade", format_name="PNG", scale=2.0)
        social = self.export_social_variants(project, target / "digital")
        for part in (pdf, images, social):
            result.files.extend(part.files)
            result.warnings.extend(part.warnings)
        return result

    @staticmethod
    def _safe(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
        return cleaned or "sr_studio"
