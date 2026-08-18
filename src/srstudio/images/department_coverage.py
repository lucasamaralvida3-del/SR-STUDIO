from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable

from srstudio.images.association import normalize_product_name
from srstudio.images.departments import classify_product_department
from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_cli import catalog_names_from_sqlite


@dataclass(frozen=True, slots=True)
class DepartmentCoverageRow:
    department: str
    total: int
    auto_approved: int
    likely: int
    review_required: int
    without_any_image: int
    auto_approved_percent: float
    likely_percent: float
    review_required_percent: float
    without_any_image_percent: float


def department_coverage(library, catalog_names: Iterable[str]) -> tuple[DepartmentCoverageRow, ...]:
    """Report accepted/likely/review/missing coverage by conservative department."""
    search_status: dict[str, str] = {}
    rank = {"review_required": 1, "likely": 2, "auto_approved": 3}

    for asset in library.all():
        status = str(getattr(asset, "review_status", "") or "").lower()
        metadata = dict(getattr(asset, "metadata", {}) or {})
        association_status = str(metadata.get("association_status", "") or "").lower()
        kind = str(getattr(asset, "kind", "") or "").lower()
        if status in {"rejected", "reject"} or kind == "decorative" or association_status == "decorative":
            continue
        if status == "accepted":
            coverage_status = "auto_approved"
        elif association_status in {"probable", "likely"}:
            coverage_status = "likely"
        else:
            coverage_status = "review_required"

        names = (
            getattr(asset, "product_key", ""),
            getattr(asset, "product_name", ""),
            *(getattr(asset, "aliases", ()) or ()),
        )
        for value in names:
            normalized = normalize_product_name(str(value or ""))
            if not normalized:
                continue
            previous = search_status.get(normalized)
            if previous is None or rank[coverage_status] > rank[previous]:
                search_status[normalized] = coverage_status

    by_department: dict[str, Counter] = {}
    seen_catalog: set[str] = set()
    for value in catalog_names:
        display = " ".join(str(value or "").split())
        normalized = normalize_product_name(display)
        if not normalized or normalized in seen_catalog:
            continue
        seen_catalog.add(normalized)
        department = classify_product_department(display)
        counter = by_department.setdefault(department, Counter())
        counter["total"] += 1
        counter[search_status.get(normalized, "without_any_image")] += 1

    rows: list[DepartmentCoverageRow] = []
    for department, counter in by_department.items():
        total = int(counter["total"])
        denominator = max(1, total)
        rows.append(
            DepartmentCoverageRow(
                department=department,
                total=total,
                auto_approved=int(counter["auto_approved"]),
                likely=int(counter["likely"]),
                review_required=int(counter["review_required"]),
                without_any_image=int(counter["without_any_image"]),
                auto_approved_percent=round(100.0 * counter["auto_approved"] / denominator, 2),
                likely_percent=round(100.0 * counter["likely"] / denominator, 2),
                review_required_percent=round(100.0 * counter["review_required"] / denominator, 2),
                without_any_image_percent=round(100.0 * counter["without_any_image"] / denominator, 2),
            )
        )
    rows.sort(key=lambda row: (-row.total, row.department))
    return tuple(rows)


def payload(rows: Iterable[DepartmentCoverageRow]) -> dict:
    values = list(rows)
    return {
        "departments": [asdict(row) for row in values],
        "catalog_products": sum(row.total for row in values),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coverage Produto↔Imagem por departamento.")
    parser.add_argument("--library", required=True)
    parser.add_argument("--product-db", default=None)
    parser.add_argument("--catalog-name", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    catalog = list(args.catalog_name)
    warnings: list[str] = []
    if args.product_db:
        try:
            catalog.extend(catalog_names_from_sqlite(args.product_db))
        except Exception as exc:
            warnings.append(f"Product database could not be read: {args.product_db}: {exc}")
    data = payload(department_coverage(SafeImageLibrary(args.library), catalog))
    if warnings:
        data["warnings"] = warnings
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
