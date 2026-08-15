from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.importers.excel.reader import ExcelImporter
from srstudio.importers.pptx.reader import PptxReader
from srstudio.importers.pptx.semantic import SemanticMapper


@dataclass(slots=True)
class ImportSummary:
    source: str
    products_added: int = 0
    cards_added: int = 0
    warnings: list[str] = field(default_factory=list)


class UnifiedImportPipeline:
    """Converte diferentes origens no mesmo modelo central do Studio."""

    def import_file(self, path: str | Path, project: StudioProject) -> ImportSummary:
        source = Path(path)
        suffix = source.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            return self._excel(source, project)
        if suffix == ".pptx":
            return self._pptx(source, project)
        raise ValueError(f"Formato não suportado: {suffix}")

    def _excel(self, path: Path, project: StudioProject) -> ImportSummary:
        result = ExcelImporter().read(path)
        summary = ImportSummary(str(path), warnings=list(result.warnings))
        for item in result.products:
            product = Product(
                code=str(item.get("code") or ""),
                ean=str(item.get("ean") or ""),
                original_name=str(item.get("name") or ""),
                price=item.get("price"),
                app_price=item.get("app_price"),
                wholesale_price=item.get("wholesale_price"),
                retail_price=item.get("retail_price"),
                unit=str(item.get("unit") or "UN"),
                quantity=str(item.get("quantity") or ""),
                cpf_limit=str(item.get("cpf_limit") or ""),
                category=str(item.get("category") or ""),
                source="excel",
                metadata={"row": item.get("row")},
            )
            project.products.append(product)
            summary.products_added += 1
        return summary

    def _pptx(self, path: Path, project: StudioProject) -> ImportSummary:
        parsed = PptxReader().read(path)
        summary = ImportSummary(str(path), warnings=list(parsed.warnings))
        mapper = SemanticMapper()
        for slide in parsed.slides:
            mapped = mapper.map_slide(slide)
            while len(project.pages) < slide.index:
                project.pages.append(type(project.pages[0])(name=f"Página {len(project.pages)+1}"))
            page = project.pages[slide.index - 1]
            for candidate in mapped:
                product = Product(
                    original_name=candidate.name,
                    price=candidate.price,
                    image_path=candidate.image_path or "",
                    source="pptx",
                    recognition_confidence=candidate.confidence,
                    metadata={"slide": slide.index},
                )
                project.products.append(product)
                project_width = max(float(slide.width or 1), 1.0)
                project_height = max(float(slide.height or 1), 1.0)
                card = ProductCard(
                    product_id=product.id,
                    x=(candidate.x / project_width) * page.width,
                    y=(candidate.y / project_height) * page.height,
                    width=max(120.0, (candidate.width / project_width) * page.width),
                    height=max(100.0, (candidate.height / project_height) * page.height),
                )
                page.cards.append(card)
                summary.products_added += 1
                summary.cards_added += 1
        return summary
