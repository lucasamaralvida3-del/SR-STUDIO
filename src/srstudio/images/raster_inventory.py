from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Protocol

from PIL import Image

from srstudio.images.association import is_product_text_candidate, normalize_product_name


@dataclass(frozen=True, slots=True)
class OcrTextLine:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]


class OcrProvider(Protocol):
    def available(self) -> bool: ...

    def recognize(self, image_path: str | Path) -> list[OcrTextLine]: ...


@dataclass(frozen=True, slots=True)
class RasterProductCandidate:
    display_name: str
    normalized_name: str
    confidence: float
    bbox: tuple[int, int, int, int]
    review_status: str = "review"
    match_method: str = "ocr-text-only"


@dataclass(slots=True)
class RasterFileInventory:
    path: str
    width: int = 0
    height: int = 0
    content_mode: str = "unknown-raster"
    ocr_lines: int = 0
    product_candidates: list[RasterProductCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RasterInventoryMetrics:
    files: int = 0
    ocr_available_files: int = 0
    ocr_lines: int = 0
    product_candidates: int = 0
    unique_products: int = 0
    composite_flyers: int = 0
    single_product_rasters: int = 0
    unknown_rasters: int = 0


@dataclass(slots=True)
class RasterInventoryReport:
    metrics: RasterInventoryMetrics
    files: list[RasterFileInventory]
    warnings: list[str] = field(default_factory=list)


class TesseractCliProvider:
    """Optional OCR adapter with no Python/runtime dependency beyond the CLI.

    The SR Studio core does not require Tesseract. If the executable is absent the
    provider reports unavailable and raster files remain unclassified instead of
    silently falling back to unreliable filename associations.
    """

    def __init__(
        self,
        *,
        executable: str = "tesseract",
        language: str = "por",
        psm: int = 11,
        minimum_word_confidence: float = 40.0,
        timeout_seconds: int = 60,
    ) -> None:
        self.executable = executable
        self.language = language
        self.psm = int(psm)
        self.minimum_word_confidence = float(minimum_word_confidence)
        self.timeout_seconds = int(timeout_seconds)

    def available(self) -> bool:
        return bool(shutil.which(self.executable))

    def recognize(self, image_path: str | Path) -> list[OcrTextLine]:
        if not self.available():
            raise RuntimeError(f"OCR executable not available: {self.executable}")
        command = [
            self.executable,
            str(image_path),
            "stdout",
            "-l",
            self.language,
            "--psm",
            str(self.psm),
            "tsv",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Tesseract failed ({completed.returncode}): {detail[:500]}")
        return parse_tesseract_tsv(
            completed.stdout,
            minimum_word_confidence=self.minimum_word_confidence,
        )


def parse_tesseract_tsv(
    payload: str,
    *,
    minimum_word_confidence: float = 40.0,
) -> list[OcrTextLine]:
    """Parse Tesseract TSV into line-level text/bboxes without OCR dependencies."""
    reader = csv.DictReader(payload.splitlines(), delimiter="\t")
    grouped: dict[tuple[str, str, str, str], list[tuple[str, float, tuple[int, int, int, int]]]] = {}
    order: list[tuple[str, str, str, str]] = []
    for row in reader:
        text = " ".join(str(row.get("text", "") or "").split())
        if not text:
            continue
        try:
            confidence = float(row.get("conf", "-1") or -1)
            left = int(row.get("left", "0") or 0)
            top = int(row.get("top", "0") or 0)
            width = int(row.get("width", "0") or 0)
            height = int(row.get("height", "0") or 0)
        except (TypeError, ValueError):
            continue
        if confidence < minimum_word_confidence:
            continue
        key = (
            str(row.get("page_num", "1")),
            str(row.get("block_num", "0")),
            str(row.get("par_num", "0")),
            str(row.get("line_num", "0")),
        )
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append((text, confidence, (left, top, width, height)))

    result: list[OcrTextLine] = []
    for key in order:
        words = grouped[key]
        text = " ".join(word for word, _, _ in words)
        confidence = sum(item[1] for item in words) / max(1, len(words))
        x1 = min(item[2][0] for item in words)
        y1 = min(item[2][1] for item in words)
        x2 = max(item[2][0] + item[2][2] for item in words)
        y2 = max(item[2][1] + item[2][3] for item in words)
        result.append(OcrTextLine(text, confidence, (x1, y1, x2 - x1, y2 - y1)))
    return result


class RasterOcrInventory:
    """Discover product-name evidence in raster-only flyers without auto-linking images.

    OCR can recover text when PPTX structure is unavailable, but the full raster is
    not automatically stored as the product image. Every OCR candidate remains
    `review`; a later spatial/card segmentation stage must provide independent
    Product↔Image evidence before promotion.
    """

    def __init__(self, provider: OcrProvider) -> None:
        self.provider = provider

    def scan(self, sources: Iterable[str | Path]) -> RasterInventoryReport:
        files: list[RasterFileInventory] = []
        warnings: list[str] = []
        unique_products: set[str] = set()

        for item in sources:
            path = Path(item)
            if path.is_dir():
                candidates = sorted(
                    candidate
                    for candidate in path.rglob("*")
                    if candidate.is_file() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
                )
            elif path.is_file():
                candidates = [path]
            else:
                warnings.append(f"Missing raster source: {path}")
                continue
            for candidate in candidates:
                files.append(self.scan_file(candidate))
                unique_products.update(row.normalized_name for row in files[-1].product_candidates)

        metrics = RasterInventoryMetrics(
            files=len(files),
            ocr_available_files=sum(not item.warnings for item in files),
            ocr_lines=sum(item.ocr_lines for item in files),
            product_candidates=sum(len(item.product_candidates) for item in files),
            unique_products=len(unique_products),
            composite_flyers=sum(item.content_mode == "composite-flyer" for item in files),
            single_product_rasters=sum(item.content_mode == "single-product-raster" for item in files),
            unknown_rasters=sum(item.content_mode == "unknown-raster" for item in files),
        )
        return RasterInventoryReport(metrics, files, warnings)

    def scan_file(self, path: str | Path) -> RasterFileInventory:
        source = Path(path)
        try:
            with Image.open(source) as image:
                width, height = image.size
        except OSError as exc:
            return RasterFileInventory(str(source), warnings=[f"Unreadable raster: {exc}"])

        if not self.provider.available():
            return RasterFileInventory(
                str(source),
                width=width,
                height=height,
                warnings=["OCR provider unavailable"],
            )

        try:
            lines = self.provider.recognize(source)
        except Exception as exc:
            return RasterFileInventory(
                str(source),
                width=width,
                height=height,
                warnings=[f"OCR failed: {exc}"],
            )

        product_candidates: list[RasterProductCandidate] = []
        seen: set[tuple[str, tuple[int, int, int, int]]] = set()
        for line in lines:
            if not is_product_text_candidate(line.text):
                continue
            normalized = normalize_product_name(line.text)
            key = (normalized, line.bbox)
            if not normalized or key in seen:
                continue
            seen.add(key)
            product_candidates.append(
                RasterProductCandidate(
                    display_name=line.text,
                    normalized_name=normalized,
                    confidence=max(0.0, min(0.89, line.confidence / 100.0)),
                    bbox=line.bbox,
                )
            )

        if len(product_candidates) >= 2:
            content_mode = "composite-flyer"
        elif len(product_candidates) == 1:
            content_mode = "single-product-raster"
        else:
            content_mode = "unknown-raster"

        return RasterFileInventory(
            path=str(source),
            width=width,
            height=height,
            content_mode=content_mode,
            ocr_lines=len(lines),
            product_candidates=product_candidates,
        )


def report_payload(report: RasterInventoryReport) -> dict:
    return {
        "metrics": asdict(report.metrics),
        "files": [
            {
                **{key: value for key, value in asdict(item).items() if key != "product_candidates"},
                "product_candidates": [asdict(row) for row in item.product_candidates],
            }
            for item in report.files
        ],
        "warnings": list(report.warnings),
    }


def write_report(path: str | Path, report: RasterInventoryReport) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(report_payload(report), ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(target)
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventaria texto de produto em encartes raster usando OCR opcional e review-first."
    )
    parser.add_argument("sources", nargs="+", help="Imagens ou diretórios raster")
    parser.add_argument("--tesseract", default="tesseract", help="Executável Tesseract")
    parser.add_argument("--language", default="por", help="Idioma Tesseract")
    parser.add_argument("--psm", type=int, default=11, help="Page segmentation mode")
    parser.add_argument("--report", default=None, help="Grava JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    provider = TesseractCliProvider(
        executable=args.tesseract,
        language=args.language,
        psm=args.psm,
    )
    report = RasterOcrInventory(provider).scan(args.sources)
    payload = report_payload(report)
    if args.report:
        payload["report_path"] = str(write_report(args.report, report))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
