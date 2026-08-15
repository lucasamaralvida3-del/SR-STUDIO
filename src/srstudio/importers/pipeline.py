from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.importers.excel.reader import ExcelImporter
from srstudio.importers.pptx.reader import PptxImporter
from srstudio.importers.pptx.semantic import SemanticMapper


@dataclass(slots=True)
class ImportSummary:
    source: str
    products_added: int = 0
    cards_added: int = 0
    warnings: list[str] = field(default_factory=list)


class UnifiedImportPipeline:
    """Converte Excel/PPTX para o mesmo modelo central do SR Studio."""

    def import_file(self, path: str | Path, project: StudioProject) -> ImportSummary:
        source = Path(path)
        suffix = source.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            return self._excel(source, project)
        if suffix == ".pptx":
            return self._pptx(source, project)
        raise ValueError(f"Formato não suportado: {suffix}")

    def _excel(self, path: Path, project: StudioProject) -> ImportSummary:
        result = ExcelImporter().import_file(path)
        warnings = [f"Linha {issue.row}: {issue.message}" for issue in result.issues]
        summary = ImportSummary(str(path), warnings=warnings)
        for item in result.products:
            product = Product(
                code=str(item.get("code") or ""),
                ean=str(item.get("ean") or ""),
                original_name=str(item.get("name") or ""),
                price=item.get("promo_price") or item.get("retail_price"),
                app_price=item.get("app_price"),
                wholesale_price=item.get("wholesale_price"),
                retail_price=item.get("retail_price"),
                unit=str(item.get("unit") or "UN"),
                cpf_limit=str(item.get("limit") or ""),
                category=str(item.get("category") or ""),
                validity=str(item.get("validity") or ""),
                source="excel",
                metadata={"source_row": item.get("source_row")},
            )
            project.products.append(product)
            summary.products_added += 1
        return summary

    def _pptx(self, path: Path, project: StudioProject) -> ImportSummary:
        parsed = PptxImporter().import_file(path)
        summary = ImportSummary(str(path), warnings=list(parsed.warnings))
        mapper = SemanticMapper()
        for slide in parsed.slides:
            mapped = mapper.map_slide(slide)
            while len(project.pages) < slide.index:
                project.pages.append(Page(name=f"Página {len(project.pages) + 1}"))
            page = project.pages[slide.index - 1]
            max_x = max((element.x + element.width for element in slide.elements), default=1)
            max_y = max((element.y + element.height for element in slide.elements), default=1)
            for candidate in mapped:
                name_element = candidate.name
                price_element = candidate.price
                image_element = candidate.image
                source_elements = [element for element in (name_element, price_element, image_element) if element is not None]
                if not source_elements:
                    continue
                left = min(element.x for element in source_elements)
                top = min(element.y for element in source_elements)
                right = max(element.x + element.width for element in source_elements)
                bottom = max(element.y + element.height for element in source_elements)
                product = Product(
                    original_name=name_element.text if name_element is not None else "Produto importado",
                    price=SemanticMapper._price_value(price_element.text) if price_element is not None else None,
                    source="pptx",
                    recognition_confidence=candidate.confidence,
                    metadata={
                        "slide": slide.index,
                        "pptx_media_path": image_element.media_path if image_element is not None else "",
                    },
                )
                project.products.append(product)
                card = ProductCard(
                    product_id=product.id,
                    x=(left / max(max_x, 1)) * page.width,
                    y=(top / max(max_y, 1)) * page.height,
                    width=max(120.0, ((right - left) / max(max_x, 1)) * page.width),
                    height=max(100.0, ((bottom - top) / max(max_y, 1)) * page.height),
                )
                page.cards.append(card)
                summary.products_added += 1
                summary.cards_added += 1
        return summary
