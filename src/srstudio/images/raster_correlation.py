from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from srstudio.images.association import (
    is_product_text_candidate,
    normalize_product_name,
    product_name_similarity,
)
from srstudio.images.corpus_training import _PRICE_TEXT_RE
from srstudio.images.raster_inventory import RasterOcrInventory, TesseractCliProvider


@dataclass(frozen=True, slots=True)
class RasterCropCandidate:
    product_name: str
    normalized_name: str
    crop_bbox: tuple[int, int, int, int]
    confidence: float
    extraction_method: str = "pptx-structured-card-fallback"
    contains_text_probability: float = 1.0
    contains_price_probability: float = 0.0
    review_status: str = "review"


@dataclass(slots=True)
class RasterSlideCorrelation:
    raster_path: str
    pptx_path: str
    slide_index: int = 0
    confidence: float = 0.0
    matched_products: int = 0
    structured_products: list[str] = field(default_factory=list)
    raster_products: list[str] = field(default_factory=list)
    embedded_image_elements: int = 0
    source_preference: str = "unresolved"
    crop_candidates: list[RasterCropCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PptxRasterCorrelator:
    """Correlate full-page raster exports to structured PPTX slides.

    OCR is only a bridge for finding the matching slide. Once matched, PPTX
    structure is the authority. If the slide contains embedded image elements the
    original PPTX asset is preferred and no raster crop is generated. Card crops
    are a review-only fallback for slides with no usable embedded image.
    """

    def __init__(self, importer: Any | None = None, raster_inventory: Any | None = None) -> None:
        if importer is None:
            from srstudio.importers.pptx.reader import PptxImporter

            importer = PptxImporter()
        self.importer = importer
        self.raster_inventory = raster_inventory

    def correlate(
        self,
        pptx_path: str | Path,
        raster_paths: Iterable[str | Path],
    ) -> list[RasterSlideCorrelation]:
        pptx = Path(pptx_path)
        imported = self.importer.import_file(pptx)
        structured = [self._slide_structure(slide) for slide in imported.slides]
        result: list[RasterSlideCorrelation] = []

        for item in raster_paths:
            raster = Path(item)
            row = RasterSlideCorrelation(str(raster), str(pptx))
            if not raster.is_file():
                row.warnings.append("Raster source missing")
                result.append(row)
                continue
            if self.raster_inventory is None:
                row.warnings.append("Raster OCR inventory unavailable")
                result.append(row)
                continue
            inventory = self.raster_inventory.scan_file(raster)
            if inventory.warnings:
                row.warnings.extend(inventory.warnings)
            raster_products = [candidate.normalized_name for candidate in inventory.product_candidates]
            row.raster_products = raster_products
            if not raster_products:
                row.warnings.append("No raster product text available for correlation")
                result.append(row)
                continue

            ranked = [
                self._slide_match(raster_products, slide_data["products"], slide_index=index)
                for index, slide_data in enumerate(structured, start=1)
            ]
            ranked.sort(key=lambda item: (item["score"], item["matched"]), reverse=True)
            best = ranked[0] if ranked else {"score": 0.0, "matched": 0, "slide_index": 0}
            second_score = ranked[1]["score"] if len(ranked) > 1 else 0.0
            margin = best["score"] - second_score
            if best["matched"] == 0 or best["score"] < 0.42:
                row.warnings.append("No structured slide reached the raster correlation gate")
                result.append(row)
                continue

            slide_index = int(best["slide_index"])
            slide_data = structured[slide_index - 1]
            confidence = min(0.98, 0.58 * best["score"] + 0.30 * min(1.0, margin * 2.5) + 0.12)
            row.slide_index = slide_index
            row.confidence = round(confidence, 6)
            row.matched_products = int(best["matched"])
            row.structured_products = list(slide_data["products"])
            row.embedded_image_elements = int(slide_data["embedded_images"])

            if row.embedded_image_elements > 0:
                row.source_preference = "embedded-original"
                result.append(row)
                continue

            row.source_preference = "raster-review-fallback"
            try:
                with Image.open(raster) as image:
                    raster_size = image.size
            except OSError as exc:
                row.warnings.append(f"Raster dimensions unavailable: {exc}")
                result.append(row)
                continue
            row.crop_candidates = self._review_crops(slide_data, raster_size)
            result.append(row)
        return result

    @staticmethod
    def _slide_structure(slide: Any) -> dict:
        product_elements = [
            element
            for element in slide.elements
            if element.kind == "text" and is_product_text_candidate(element.text)
        ]
        prices = [
            element
            for element in slide.elements
            if element.kind == "text" and _PRICE_TEXT_RE.search(element.text or "")
        ]
        return {
            "slide": slide,
            "products": [normalize_product_name(element.text) for element in product_elements],
            "product_elements": product_elements,
            "prices": prices,
            "embedded_images": sum(element.kind == "image" for element in slide.elements),
        }

    @staticmethod
    def _slide_match(raster_products: list[str], structured_products: list[str], *, slide_index: int) -> dict:
        if not raster_products or not structured_products:
            return {"score": 0.0, "matched": 0, "slide_index": slide_index}
        matched = 0
        similarities: list[float] = []
        used: set[int] = set()
        for raster_name in raster_products:
            candidates = sorted(
                (
                    (product_name_similarity(raster_name, structured_name), index)
                    for index, structured_name in enumerate(structured_products)
                    if index not in used
                ),
                reverse=True,
            )
            if not candidates:
                continue
            similarity, index = candidates[0]
            if similarity < 0.72:
                continue
            used.add(index)
            matched += 1
            similarities.append(similarity)
        if not similarities:
            return {"score": 0.0, "matched": 0, "slide_index": slide_index}
        precision = matched / max(1, len(raster_products))
        recall = matched / max(1, len(structured_products))
        text_quality = sum(similarities) / len(similarities)
        score = 0.44 * text_quality + 0.34 * precision + 0.22 * recall
        return {"score": round(score, 6), "matched": matched, "slide_index": slide_index}

    @staticmethod
    def _review_crops(slide_data: dict, raster_size: tuple[int, int]) -> list[RasterCropCandidate]:
        slide = slide_data["slide"]
        raster_w, raster_h = raster_size
        scale_x = raster_w / max(1, int(slide.width))
        scale_y = raster_h / max(1, int(slide.height))
        result: list[RasterCropCandidate] = []
        for element in slide_data["product_elements"]:
            tx, ty, tw, th = int(element.x), int(element.y), int(element.width), int(element.height)
            x1 = max(0, int((tx - max(tw * 0.45, slide.width * 0.025)) * scale_x))
            x2 = min(raster_w, int((tx + tw + max(tw * 0.45, slide.width * 0.025)) * scale_x))
            y1 = max(0, int((ty - slide.height * 0.13) * scale_y))
            y2 = min(raster_h, int((ty + th + slide.height * 0.16) * scale_y))
            bbox = (x1, y1, max(1, x2 - x1), max(1, y2 - y1))
            contains_price = 0.0
            for price in slide_data["prices"]:
                px, py, pw, ph = int(price.x), int(price.y), int(price.width), int(price.height)
                if _intersects((tx, ty - int(slide.height * .13), tw, th + int(slide.height * .29)), (px, py, pw, ph)):
                    contains_price = 1.0
                    break
            result.append(
                RasterCropCandidate(
                    product_name=element.text,
                    normalized_name=normalize_product_name(element.text),
                    crop_bbox=bbox,
                    confidence=0.45,
                    contains_price_probability=contains_price,
                )
            )
        return result


def _intersects(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return min(lx + lw, rx + rw) > max(lx, rx) and min(ly + lh, ry + rh) > max(ly, ry)


def report_payload(rows: Iterable[RasterSlideCorrelation]) -> dict:
    values = list(rows)
    return {
        "metrics": {
            "rasters": len(values),
            "correlated": sum(row.slide_index > 0 for row in values),
            "embedded_original_preferred": sum(row.source_preference == "embedded-original" for row in values),
            "raster_review_fallback": sum(row.source_preference == "raster-review-fallback" for row in values),
            "review_crop_candidates": sum(len(row.crop_candidates) for row in values),
        },
        "correlations": [
            {
                **{key: value for key, value in asdict(row).items() if key != "crop_candidates"},
                "crop_candidates": [asdict(candidate) for candidate in row.crop_candidates],
            }
            for row in values
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Correlaciona exports raster com slides PPTX sem degradar assets embedded.")
    parser.add_argument("pptx")
    parser.add_argument("rasters", nargs="+")
    parser.add_argument("--tesseract", default="tesseract")
    parser.add_argument("--language", default="por")
    parser.add_argument("--report", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    raster_inventory = RasterOcrInventory(
        TesseractCliProvider(executable=args.tesseract, language=args.language)
    )
    rows = PptxRasterCorrelator(raster_inventory=raster_inventory).correlate(args.pptx, args.rasters)
    payload = report_payload(rows)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        json.loads(temporary.read_text(encoding="utf-8"))
        temporary.replace(target)
        payload["report_path"] = str(target)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
