from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.images.library import ImageLibrary
from srstudio.importers.excel.reader import ExcelImporter
from srstudio.importers.pptx.reader import PptxElement, PptxImporter
from srstudio.importers.pptx.semantic import SemanticCard
from srstudio.importers.pptx.slot_validation import SmartSlotValidator
from srstudio.importers.pptx.smart_semantic import SmartSlotSemanticMapper
from srstudio.templates.corpus import LayoutCorpus


@dataclass(slots=True)
class ImportSummary:
    source: str
    products_added: int = 0
    cards_added: int = 0
    images_matched: int = 0
    images_learned: int = 0
    layouts_learned: int = 0
    warnings: list[str] = field(default_factory=list)


class UnifiedImportPipeline:
    """Convert Excel/Canva PPTX into the same editable SR Studio project model."""

    MIN_FUZZY_IMAGE_SCORE = 0.88

    def __init__(
        self,
        image_library: ImageLibrary | None = None,
        layout_corpus: LayoutCorpus | None = None,
    ) -> None:
        self.image_library = image_library
        self.layout_corpus = layout_corpus
        self.pptx_importer = PptxImporter()
        self.semantic_mapper = SmartSlotSemanticMapper()

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
                quantity=str(item.get("quantity") or ""),
                cpf_limit=str(item.get("limit") or ""),
                category=str(item.get("category") or ""),
                validity=str(item.get("validity") or ""),
                source="excel",
                metadata={"source_row": item.get("source_row")},
            )
            self._attach_learned_image(product, summary)
            project.products.append(product)
            summary.products_added += 1
        return summary

    def _attach_learned_image(self, product: Product, summary: ImportSummary) -> None:
        if self.image_library is None or product.image_path:
            return
        match = self.image_library.find_best_for_product(product.name)
        if match is None or match.asset.review_status != "accepted":
            return
        if match.reason == "similaridade" and match.score < self.MIN_FUZZY_IMAGE_SCORE:
            summary.warnings.append(
                f"Imagem não aplicada automaticamente em {product.name}: similaridade insuficiente ({round(match.score * 100)}%)."
            )
            return
        product.image_path = match.asset.path
        product.metadata["image_bank_asset_id"] = match.asset.id
        product.metadata["image_bank_score"] = round(match.score, 4)
        product.metadata["image_bank_reason"] = match.reason
        product.metadata["image_bank_source"] = match.asset.source
        self.image_library.record_use(match.asset.id)
        summary.images_matched += 1

    def _pptx(self, path: Path, project: StudioProject) -> ImportSummary:
        digest = hashlib.sha256(f"{path.resolve()}:{path.stat().st_mtime_ns}".encode()).hexdigest()[:16]
        media_dir = Path.home() / ".srstudio5" / "imports" / digest
        parsed = self.pptx_importer.import_file(path, media_dir=media_dir)
        summary = ImportSummary(str(path), warnings=list(parsed.warnings))
        learned_profiles: list[str] = []
        slot_stats: list[dict[str, int]] = []

        for slide in parsed.slides:
            while len(project.pages) < slide.index:
                project.pages.append(Page(name=f"Página {len(project.pages) + 1}"))
            page = project.pages[slide.index - 1]
            page.name = f"Slide {slide.index}"
            page.width = 1080.0
            page.height = 1080.0 * (slide.height / max(slide.width, 1))
            if str(slide.background).startswith("#"):
                page.background = slide.background
            page.cards.clear()
            page.elements.clear()

            mapped = self.semantic_mapper.map_slide(slide)
            safe_mapped, validation = SmartSlotValidator.select(mapped, slide)
            slot_stats.append(
                {
                    "slide": slide.index,
                    "detected": validation.detected,
                    "accepted": validation.accepted,
                    "rejected": validation.rejected,
                }
            )
            if validation.rejected:
                summary.warnings.append(
                    f"Slide {slide.index}: {validation.rejected} associação(ões) ambígua(s) ignorada(s) para proteger o layout."
                )

            if self.layout_corpus is not None:
                profile = self.layout_corpus.observe(slide, mapped, str(path))
                if profile is not None:
                    learned_profiles.append(profile.id)
                    summary.layouts_learned += 1

            slot_bindings: dict[int, tuple[str, str]] = {}
            for candidate in safe_mapped:
                semantic_elements = self._semantic_elements(candidate)
                if not semantic_elements or candidate.bounds is None:
                    continue
                left, top, right, bottom = candidate.bounds
                name_element = candidate.name
                image_element = candidate.image
                product_name = name_element.text if name_element is not None else "Produto importado"
                image_path = (
                    image_element.media_path
                    if image_element is not None and Path(image_element.media_path).exists()
                    else ""
                )
                image_asset_id = ""
                if self.image_library is not None and image_path and name_element is not None:
                    try:
                        asset = self.image_library.learn_product_image(
                            image_path,
                            product_name,
                            confidence=candidate.confidence,
                            source_file=path.name,
                            slide_index=slide.index,
                            metadata={
                                "source_file": str(path),
                                "card_bounds": list(candidate.bounds),
                                "crop": dict(image_element.metadata.get("crop") or {}) if image_element else {},
                                "smart_slot_validated": True,
                            },
                        )
                        image_path = asset.path
                        image_asset_id = asset.id
                        summary.images_learned += 1
                    except (OSError, ValueError):
                        pass

                unit = self._unit_text(candidate.unit.text if candidate.unit is not None else "UN")
                product = Product(
                    original_name=product_name,
                    price=candidate.price_value,
                    app_price=(candidate.secondary_price.value if candidate.secondary_price is not None else None),
                    unit=unit,
                    image_path=image_path,
                    source="pptx",
                    recognition_confidence=candidate.confidence,
                    metadata={
                        "slide": slide.index,
                        "source_file": str(path),
                        "image_bank_asset_id": image_asset_id,
                        "canva_import_v2": True,
                        "canva_native_visual": True,
                        "smart_slot_validated": True,
                        "price_split": bool(candidate.price_cluster and candidate.price_cluster.complete is None),
                    },
                )
                project.products.append(product)
                card = ProductCard(
                    product_id=product.id,
                    x=(left / max(slide.width, 1)) * page.width,
                    y=(top / max(slide.height, 1)) * page.height,
                    width=max(24.0, ((right - left) / max(slide.width, 1)) * page.width),
                    height=max(24.0, ((bottom - top) / max(slide.height, 1)) * page.height),
                    locked=True,
                    z_index=min((int(item.metadata.get("z_index", 0)) for item in semantic_elements), default=0),
                    overrides={
                        "imported_from_canva": True,
                        "canva_native_visual": True,
                        "slot_detected": True,
                        "slot_validated": True,
                        "slot_filled": False,
                        "slot_template_product_id": product.id,
                        "hidden": True,
                        "imported_style": dict(candidate.style_spec),
                        "recognition_confidence": candidate.confidence,
                    },
                )
                page.cards.append(card)
                slot_bindings.update(self._candidate_slot_bindings(candidate, card.id))
                summary.products_added += 1
                summary.cards_added += 1

            # Preserve the complete Canva slide as the visual layer. Semantic cards are
            # locked/hidden hit regions. Only validated local associations receive a
            # slot binding, so replacing one product can never rewrite a large unrelated
            # region of the slide.
            for element in slide.elements:
                converted = self._pptx_element(element, slide.width, slide.height, page.width, page.height)
                if not converted:
                    continue
                binding = slot_bindings.get(id(element))
                if binding is not None:
                    slot_id, role = binding
                    converted["slot_id"] = slot_id
                    converted["slot_role"] = role
                    converted["template_hidden"] = bool(converted.get("hidden", False))
                    if converted.get("type") == "text":
                        converted["template_text"] = str(converted.get("text") or "")
                    elif converted.get("type") == "image":
                        converted["template_path"] = str(converted.get("path") or "")
                page.elements.append(converted)

        project.settings["pptx_source"] = str(path)
        project.settings["pptx_media_dir"] = str(media_dir)
        project.settings["canva_import_version"] = 5
        project.settings["canva_native_visual"] = True
        project.settings["canva_smart_slots"] = True
        project.settings["canva_slot_detector_version"] = 2
        project.settings["canva_slot_stats"] = slot_stats
        if learned_profiles:
            project.settings["canva_layout_profiles"] = list(dict.fromkeys(learned_profiles))
        return summary

    @staticmethod
    def _candidate_slot_bindings(candidate: SemanticCard, card_id: str) -> dict[int, tuple[str, str]]:
        bindings: dict[int, tuple[str, str]] = {}

        def bind(element: PptxElement | None, role: str) -> None:
            if element is not None:
                bindings[id(element)] = (card_id, role)

        bind(candidate.name, "name")
        bind(candidate.image, "image")
        cluster = candidate.price_cluster
        if cluster is not None:
            bind(cluster.complete, "price_complete")
            bind(cluster.currency, "price_currency")
            bind(cluster.integer, "price_integer")
            bind(cluster.cents, "price_cents")
            bind(cluster.unit, "unit")
        elif candidate.price is not None:
            bind(candidate.price, "price_complete")
        if candidate.unit is not None:
            bind(candidate.unit, "unit")

        secondary = candidate.secondary_price
        if secondary is not None:
            bind(secondary.complete, "app_price_complete")
            bind(secondary.currency, "app_price_currency")
            bind(secondary.integer, "app_price_integer")
            bind(secondary.cents, "app_price_cents")
            bind(secondary.unit, "app_unit")
        return bindings

    @staticmethod
    def _semantic_elements(candidate: SemanticCard) -> list[PptxElement]:
        elements: list[PptxElement] = []
        for item in (candidate.name, candidate.image):
            if item is not None:
                elements.append(item)
        if candidate.price_cluster is not None:
            elements.extend(candidate.price_cluster.elements)
        elif candidate.price is not None:
            elements.append(candidate.price)
        if candidate.secondary_price is not None:
            elements.extend(candidate.secondary_price.elements)
        unique: list[PptxElement] = []
        seen: set[int] = set()
        for element in elements:
            if id(element) not in seen:
                unique.append(element)
                seen.add(id(element))
        return unique

    @staticmethod
    def _unit_text(value: str) -> str:
        text = " ".join(str(value or "UN").upper().replace("/", " ").split())
        aliases = {
            "A LATA": "À LATA",
            "A GARRAFA": "À GARRAFA",
            "LT": "L",
            "GR": "G",
        }
        return aliases.get(text, text or "UN")

    @staticmethod
    def _pptx_element(element: PptxElement, sw: int, sh: int, pw: float, ph: float) -> dict | None:
        x = (element.x / max(sw, 1)) * pw
        y = (element.y / max(sh, 1)) * ph
        width = (element.width / max(sw, 1)) * pw
        height = (element.height / max(sh, 1)) * ph
        metadata = element.metadata
        common = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "source": "pptx",
            "name": element.name,
            "z_index": int(metadata.get("z_index", 0)),
            "rotation": float(metadata.get("rotation", 0.0) or 0.0),
            "opacity": float(metadata.get("opacity", 1.0) or 1.0),
            "grouped": bool(metadata.get("grouped", False)),
            "group_depth": int(metadata.get("group_depth", 0) or 0),
        }
        if element.kind == "text":
            font_size_pt = float(metadata.get("font_size_pt", 0.0) or 0.0)
            return {
                **common,
                "type": "text",
                "text": element.text,
                "font_name": str(metadata.get("font_name") or ""),
                "font_size": font_size_pt if font_size_pt > 0 else max(8, min(64, height * 0.42)),
                "bold": bool(metadata.get("bold", False)),
                "italic": bool(metadata.get("italic", False)),
                "align": str(metadata.get("align") or ""),
                "fill": str(metadata.get("fill") or "#162033"),
            }
        if element.kind == "image" and element.media_path and Path(element.media_path).exists():
            return {
                **common,
                "type": "image",
                "path": element.media_path,
                "crop": dict(metadata.get("crop") or {}),
                "fill_rect": dict(metadata.get("fill_rect") or {}),
                "image_fit": "cover" if metadata.get("crop") or metadata.get("picture_fill") else "contain",
                "picture_fill": bool(metadata.get("picture_fill", False)),
                "flip_h": bool(metadata.get("flip_h", False)),
                "flip_v": bool(metadata.get("flip_v", False)),
            }
        if element.kind == "shape":
            raw_fill = str(metadata.get("fill") or "")
            raw_outline = str(metadata.get("outline") or "")
            fill = raw_fill if raw_fill.startswith("#") else ""
            outline = raw_outline if raw_outline.startswith("#") else ""
            # Canva frequently exports transparent/no-fill helper shapes. The old
            # fallback painted them white, which created the large white blocks seen
            # over product cards after import.
            if not fill and not outline:
                return None
            return {
                **common,
                "type": "rect",
                "fill": fill,
                "outline": outline,
            }
        return None