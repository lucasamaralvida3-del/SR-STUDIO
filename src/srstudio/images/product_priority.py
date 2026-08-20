from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from srstudio.images.association import is_product_text_candidate, normalize_product_name


_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


@dataclass(frozen=True, slots=True)
class ProductPriorityRow:
    display_name: str
    normalized_name: str
    occurrence_count: int
    source_count: int
    catalog_present: bool
    priority_score: float


@dataclass(frozen=True, slots=True)
class ProductPriorityReport:
    files_seen: int
    exact_documents: int
    logical_documents: int
    product_occurrences: int
    unique_products: int
    rows: tuple[ProductPriorityRow, ...]
    warnings: tuple[str, ...] = ()


def scan_product_priority(
    sources: Iterable[str | Path],
    *,
    catalog_names: Iterable[str] = (),
) -> ProductPriorityReport:
    """Count structured product text independently from image association.

    Archive copies and exact inner-PPTX duplicates are collapsed by SHA-256. A
    conservative semantic fingerprint of slide/product occurrences additionally
    collapses harmless export copies so they do not inflate priority.
    """
    catalog = {
        normalized
        for value in catalog_names
        if (normalized := normalize_product_name(str(value)))
    }
    warnings: list[str] = []
    documents: dict[str, tuple[str, list[list[str]]]] = {}
    files_seen = 0

    for label, blob_or_path in _discover_pptx_sources(sources, warnings):
        files_seen += 1
        try:
            if isinstance(blob_or_path, Path):
                blob = blob_or_path.read_bytes()
            else:
                blob = blob_or_path
            exact_sha = hashlib.sha256(blob).hexdigest()
            if exact_sha in documents:
                continue
            slide_products = _structured_product_occurrences(blob)
            documents[exact_sha] = (label, slide_products)
        except Exception as exc:
            warnings.append(f"{label}: {exc}")

    logical: dict[str, tuple[str, list[list[str]]]] = {}
    for exact_sha, (label, slides) in documents.items():
        semantic_payload = json.dumps(slides, ensure_ascii=False, sort_keys=False, separators=(",", ":"))
        semantic_sha = hashlib.sha256(semantic_payload.encode("utf-8")).hexdigest()
        logical.setdefault(semantic_sha, (label, slides))

    occurrences: Counter[str] = Counter()
    display_names: Counter[tuple[str, str]] = Counter()
    source_sets: dict[str, set[str]] = defaultdict(set)
    for semantic_sha, (_, slides) in logical.items():
        for products in slides:
            for original in products:
                normalized = normalize_product_name(original)
                if not normalized:
                    continue
                occurrences[normalized] += 1
                display_names[(normalized, original)] += 1
                source_sets[normalized].add(semantic_sha)

    rows: list[ProductPriorityRow] = []
    for normalized, count in occurrences.items():
        display = max(
            (name for key, name in display_names if key == normalized),
            key=lambda name: (display_names[(normalized, name)], len(name)),
            default=normalized,
        )
        source_count = len(source_sets[normalized])
        in_catalog = normalized in catalog
        # Frequency leads; independent sources and catalog presence break ties.
        score = float(count) + 1.75 * source_count + (2.0 if in_catalog else 0.0)
        rows.append(
            ProductPriorityRow(
                display_name=display,
                normalized_name=normalized,
                occurrence_count=count,
                source_count=source_count,
                catalog_present=in_catalog,
                priority_score=round(score, 4),
            )
        )
    rows.sort(
        key=lambda row: (row.priority_score, row.occurrence_count, row.source_count, row.normalized_name),
        reverse=True,
    )
    return ProductPriorityReport(
        files_seen=files_seen,
        exact_documents=len(documents),
        logical_documents=len(logical),
        product_occurrences=sum(occurrences.values()),
        unique_products=len(rows),
        rows=tuple(rows),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def report_payload(report: ProductPriorityReport) -> dict:
    return {
        "metrics": {
            "files_seen": report.files_seen,
            "exact_documents": report.exact_documents,
            "logical_documents": report.logical_documents,
            "product_occurrences": report.product_occurrences,
            "unique_products": report.unique_products,
        },
        "rows": [asdict(row) for row in report.rows],
        "warnings": list(report.warnings),
    }


def _discover_pptx_sources(sources: Iterable[str | Path], warnings: list[str]):
    seen_paths: set[str] = set()
    for item in sources:
        path = Path(item)
        if path.is_dir():
            candidates = sorted([*path.rglob("*.pptx"), *path.rglob("*.zip")])
            yield from _discover_pptx_sources(candidates, warnings)
            continue
        if not path.is_file():
            warnings.append(f"Missing priority source: {path}")
            continue
        resolved = str(path.resolve())
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        if path.suffix.lower() == ".pptx":
            yield str(path), path
            continue
        if path.suffix.lower() != ".zip":
            warnings.append(f"Unsupported priority source: {path}")
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir() or not member.filename.lower().endswith(".pptx"):
                        continue
                    with archive.open(member) as handle:
                        yield f"{path}!{member.filename}", handle.read()
        except (OSError, zipfile.BadZipFile) as exc:
            warnings.append(f"{path}: {exc}")


def _structured_product_occurrences(blob: bytes) -> list[list[str]]:
    slides: list[tuple[int, list[str]]] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as presentation:
        for name in presentation.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            stem = Path(name).stem
            try:
                index = int(stem.removeprefix("slide"))
            except ValueError:
                continue
            root = ET.fromstring(presentation.read(name))
            products: list[str] = []
            for shape in root.findall(f".//{{{_P_NS}}}sp"):
                text = " ".join(
                    "".join(node.itertext()).strip()
                    for node in shape.findall(f".//{{{_A_NS}}}t")
                    if "".join(node.itertext()).strip()
                )
                text = " ".join(text.split())
                if text and is_product_text_candidate(text):
                    products.append(text)
            slides.append((index, products))
    slides.sort(key=lambda item: item[0])
    return [products for _, products in slides]
