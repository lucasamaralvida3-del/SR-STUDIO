from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.importers.excel.reader import ExcelImporter
from srstudio.importers.pptx.reader import PptxElement, PptxImporter
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
        digest = hashlib.sha256(f"{path.resolve()}:{path.stat().st_mtime_ns}".encode()).hexdigest()[:16]
        media_dir = Path.home() / ".srstudio5" / "imports" / digest
        parsed = PptxImporter().import_file(path, media_dir=media_dir)
        summary = ImportSummary(str(path), warnings=list(parsed.warnings))
        mapper = SemanticMapper()

        for slide in parsed.slides:
            while len(project.pages) < slide.index:
                project.pages.append(Page(name=f"Página {len(project.pages) + 1}"))
            page = project.pages[slide.index - 1]
            page.name = f"Slide {slide.index}"
            page.width = 1080.0
            page.height = 1080.0 * (slide.height / max(slide.width, 1))
            page.cards.clear()
            page.elements.clear()

            mapped = mapper.map_slide(slide)
            used: set[int] = set()
            for candidate in mapped:
                elements = [item for item in (candidate.name, candidate.price, candidate.image) if item is not None]
                if not elements:
                    continue
                used.update(id(item) for item in elements)
                left = min(item.x for item in elements)
                top = min(item.y for item in elements)
                right = max(item.x + item.width for item in elements)
                bottom = max(item.y + item.height for item in elements)
                name_element = candidate.name
                price_element = candidate.price
                image_element = candidate.image
                product = Product(
                    original_name=name_element.text if name_element is not None else "Produto importado",
                    price=SemanticMapper._price_value(price_element.text) if price_element is not None else None,
                    image_path=image_element.media_path if image_element is not None and Path(image_element.media_path).exists() else "",
                    source="pptx",
                    recognition_confidence=candidate.confidence,
                    metadata={"slide": slide.index, "source_file": str(path)},
                )
                project.products.append(product)
                card = ProductCard(
                    product_id=product.id,
                    x=(left / max(slide.width, 1)) * page.width,
                    y=(top / max(slide.height, 1)) * page.height,
                    width=max(80.0, ((right - left) / max(slide.width, 1)) * page.width),
                    height=max(70.0, ((bottom - top) / max(slide.height, 1)) * page.height),
                )
                page.cards.append(card)
                summary.products_added += 1
                summary.cards_added += 1

            for element in slide.elements:
                if id(element) in used:
                    continue
                converted = self._pptx_element(element, slide.width, slide.height, page.width, page.height)
                if converted:
                    page.elements.append(converted)

        project.settings["pptx_source"] = str(path)
        project.settings["pptx_media_dir"] = str(media_dir)
        return summary

    @staticmethod
    def _pptx_element(element: PptxElement, sw: int, sh: int, pw: float, ph: float) -> dict | None:
        x = (element.x / max(sw, 1)) * pw
        y = (element.y / max(sh, 1)) * ph
        width = (element.width / max(sw, 1)) * pw
        height = (element.height / max(sh, 1)) * ph
        common = {"x": x, "y": y, "width": width, "height": height, "source": "pptx", "name": element.name}
        if element.kind == "text":
            return {**common, "type": "text", "text": element.text, "font_size": max(10, min(54, height * 0.45)), "fill": "#162033"}
        if element.kind == "image" and element.media_path and Path(element.media_path).exists():
            return {**common, "type": "image", "path": element.media_path}
        if element.kind == "shape":
            return {**common, "type": "rect", "fill": "#FFFFFF", "outline": "#D9E1EC"}
        return None
