from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from srstudio.core.models import StudioProject
from srstudio.export.renderer import FlyerRenderer


@dataclass(slots=True)
class ExportResult:
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExportService:
    """Exportação centralizada de campanhas para múltiplos canais."""

    def __init__(self) -> None:
        self.renderer = FlyerRenderer()

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
                image = image.convert("RGB")
                image.save(path, "JPEG", quality=95, optimize=True)
            else:
                image.save(path, "PNG", optimize=True)
            result.files.append(path)
        return result

    def export_social_variants(self, project: StudioProject, output_dir: str | Path) -> ExportResult:
        target = Path(output_dir)
        result = ExportResult()
        rendered = self.export_images(project, target / "original", format_name="PNG", scale=1.0)
        result.files.extend(rendered.files)
        for path in rendered.files:
            with Image.open(path) as image:
                instagram = self._fit_canvas(image, (1080, 1350))
                instagram_path = target / "instagram" / path.name
                instagram_path.parent.mkdir(parents=True, exist_ok=True)
                instagram.save(instagram_path, "PNG", optimize=True)
                result.files.append(instagram_path)

                whatsapp = self._fit_canvas(image, (1080, 1920))
                whatsapp_path = target / "whatsapp_status" / path.name
                whatsapp_path.parent.mkdir(parents=True, exist_ok=True)
                whatsapp.save(whatsapp_path, "PNG", optimize=True)
                result.files.append(whatsapp_path)
        return result

    @staticmethod
    def _fit_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
        canvas = Image.new("RGB", size, "white")
        copy = image.convert("RGB")
        copy.thumbnail(size, Image.Resampling.LANCZOS)
        x = (size[0] - copy.width) // 2
        y = (size[1] - copy.height) // 2
        canvas.paste(copy, (x, y))
        return canvas

    @staticmethod
    def _safe(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
        return cleaned or "sr_studio"
