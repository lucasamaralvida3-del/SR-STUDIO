from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from srstudio.images.association import normalize_product_name
from srstudio.images.department_coverage import department_coverage, payload as department_payload
from srstudio.images.library_audit import audit_library, payload as audit_payload
from srstudio.images.lookup import ProductImageLookupService
from srstudio.images.product_priority import report_payload as priority_payload
from srstudio.images.product_priority import scan_product_priority
from srstudio.images.review_contact_sheet import build_review_dataset, dataset_payload, render_contact_sheet
from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_cli import catalog_names_from_sqlite


QUERY_SET = (
    "ARROZ VASCONCELOS 5KG",
    "ARROZ PATOSUL 5KG",
    "FEIJAO PARANA 1KG",
    "CAFE VASCONCELOS 500G",
    "LEITE TRIANGULO 1L",
    "FLOCAO SINHA 400G",
    "DETERGENTE YPE 500ML",
    "MONSTER 473ML",
    "TODDY 370G",
    "TODDY 750G",
    "BANANA NANICA",
    "TOMATE PERA",
    "CARNE MOIDA",
    "COSTELA RIPA",
)

FUZZY_QUERY_SET = (
    "ARROZ VASCONCELO 5KG",
    "ARROZ PATOSU 5KG",
    "FEIJAO PARAN 1KG",
    "CAFE VASCONCELO 500G",
    "LEITE TRIANGUL 1L",
    "FLOCAO SINH 400G",
    "DETERGENTE YP 500ML",
    "MONSTE 473ML",
    "TODD 370G",
    "TODD 750G",
)

# These are identity-safety checks, not expected positive matches. A lower-
# specificity query may return no candidate, but it must never silently become
# an exact/alias or accepted candidate for a materially different SKU/variant.
NEGATIVE_CASES = (
    ("TODDY 370G", "TODDY 750G"),
    ("ARROZ PATOSUL 1KG", "ARROZ PATOSUL 5KG"),
    ("LEITE TRIANGULO 200ML", "LEITE TRIANGULO 1L"),
    ("MONSTER ZERO 473ML", "MONSTER 473ML"),
    ("DETERGENTE YPE LIMAO 500ML", "DETERGENTE YPE NEUTRO 500ML"),
    ("REFRIGERANTE COLA ZERO 2L", "REFRIGERANTE COLA TRADICIONAL 2L"),
)


_AUDIT_REQUIRED_NONNEGATIVE_INT_METRICS = (
    "associations_without_provenance",
    "negative_invariant_violations",
    "duplicate_logical_associations",
    "logical_associations_total",
    "unique_logical_associations",
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _timing(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "mean_ms": round(statistics.fmean(ordered) * 1000.0, 6),
        "p50_ms": round(statistics.median(ordered) * 1000.0, 6),
        "p95_ms": round(ordered[p95_index] * 1000.0, 6),
        "max_ms": round(max(ordered) * 1000.0, 6),
    }


def _lookup_row(service: ProductImageLookupService, query: str) -> dict:
    result = service.find_image(query)
    best = result.best_match
    asset = best.asset if best else None
    return {
        "query": query,
        "found": best is not None,
        "best_product_name": str(getattr(asset, "product_name", "") or "") if asset else "",
        "best_product_key": str(getattr(asset, "product_key", "") or "") if asset else "",
        "image_id": str(getattr(asset, "id", "") or "") if asset else "",
        "asset_review_status": str(getattr(asset, "review_status", "") or "") if asset else "",
        "asset_confidence": float(getattr(asset, "confidence", 0.0) or 0.0) if asset else 0.0,
        "confidence": result.confidence,
        "match_type": result.match_type,
        "quality_score": result.quality_score,
        "provenance": list(result.provenance),
    }


def _run_negative_invariants(service: ProductImageLookupService) -> list[dict]:
    rows: list[dict] = []
    for query, forbidden_name in NEGATIVE_CASES:
        row = _lookup_row(service, query)
        row["forbidden_product_name"] = forbidden_name
        same_forbidden = normalize_product_name(row["best_product_name"]) == normalize_product_name(forbidden_name)
        auto_or_exact = row["match_type"] in {"exact", "alias"} or row["asset_review_status"].lower() == "accepted"
        row["violated"] = bool(row["found"] and same_forbidden and auto_or_exact)
        rows.append(row)
    return rows


def _logical_association_summary(assets: list[object]) -> dict:
    identities: Counter[tuple[str, str]] = Counter()
    for asset in assets:
        product = str(getattr(asset, "product_name", "") or getattr(asset, "product_key", "") or "")
        normalized_product = normalize_product_name(product)
        metadata = dict(getattr(asset, "metadata", {}) or {})
        canonical_sha = str(metadata.get("canonical_sha256") or metadata.get("sha256") or "").strip().lower()
        if not normalized_product or not canonical_sha:
            continue
        identities[(normalized_product, canonical_sha)] += 1

    logical_total = sum(identities.values())
    unique_logical = len(identities)
    duplicate_logical = sum(count - 1 for count in identities.values() if count > 1)
    if duplicate_logical != logical_total - unique_logical:
        raise AssertionError("logical association duplicate accounting is inconsistent")

    examples = [
        {
            "normalized_product": normalized_product,
            "canonical_sha": canonical_sha,
            "count": count,
        }
        for (normalized_product, canonical_sha), count in sorted(identities.items())
        if count > 1
    ]
    return {
        "logical_associations_total": logical_total,
        "unique_logical_associations": unique_logical,
        "duplicate_logical_associations": duplicate_logical,
        "duplicate_logical_examples": examples,
    }


def _validate_audit_schema(audit_data: dict) -> None:
    metrics = audit_data.get("metrics") if isinstance(audit_data, dict) else None
    if not isinstance(metrics, dict):
        raise AssertionError("library audit metrics object is missing")
    for field in _AUDIT_REQUIRED_NONNEGATIVE_INT_METRICS:
        if field not in metrics:
            raise AssertionError(f"library audit metric is missing: {field}")
        value = metrics[field]
        if type(value) is not int or value < 0:
            raise AssertionError(f"library audit metric must be a non-negative integer: {field}")


def run(args: argparse.Namespace) -> int:
    artifact = Path(args.artifact_dir)
    library_root = Path(args.library)
    sources = [Path(value) for value in args.corpus_source]
    artifact.mkdir(parents=True, exist_ok=True)

    catalog_raw = catalog_names_from_sqlite(args.product_db)
    catalog: list[str] = []
    seen: set[str] = set()
    for name in catalog_raw:
        normalized = normalize_product_name(name)
        if normalized and normalized not in seen:
            seen.add(normalized)
            catalog.append(name)

    priority = scan_product_priority(sources, catalog_names=catalog)
    _write_json(artifact / "product-priority.json", priority_payload(priority))

    started = time.perf_counter()
    library = SafeImageLibrary(library_root)
    assets = list(library.all())
    index_load_seconds = time.perf_counter() - started

    audit_started = time.perf_counter()
    audit = audit_library(
        library,
        catalog,
        QUERY_SET,
        priority_rows=priority.rows,
        top_missing_limit=100,
    )
    audit_seconds = time.perf_counter() - audit_started
    audit_data = audit_payload(audit)

    metrics = audit_data["metrics"]
    total = int(metrics.get("catalog_products", 0))
    auto = int(metrics.get("catalog_auto_approved", 0))
    likely = int(metrics.get("catalog_likely", 0))
    review = int(metrics.get("catalog_review_required", 0))
    missing = int(metrics.get("catalog_without_any_image", 0))
    any_candidate = auto + likely + review
    coverage = {
        "total": total,
        "auto_approved": auto,
        "likely": likely,
        "review_required": review,
        "missing": missing,
        "any_candidate": any_candidate,
        "any_candidate_coverage_percent": round(100.0 * any_candidate / max(1, total), 4),
        "auto_approved_coverage_percent": round(100.0 * auto / max(1, total), 4),
    }
    _write_json(artifact / "coverage-catalog-520.json", coverage)

    departments = department_payload(department_coverage(library, catalog))
    _write_json(artifact / "coverage-departments.json", departments)

    top_missing = list(audit.priority_missing)
    top_missing_path = artifact / "top-missing-100.csv"
    with top_missing_path.open("w", newline="", encoding="utf-8") as handle:
        fields = (
            sorted({key for row in top_missing for key in row})
            if top_missing
            else ["display_name", "normalized_name", "priority_score"]
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(top_missing)

    service = ProductImageLookupService(library)
    service.refresh()
    exact_times: list[float] = []
    fuzzy_times: list[float] = []
    exact_rows = [_lookup_row(service, query) for query in QUERY_SET]
    fuzzy_rows = [_lookup_row(service, query) for query in FUZZY_QUERY_SET]
    for _ in range(20):
        for query in QUERY_SET:
            begin = time.perf_counter()
            service.find_image(query)
            exact_times.append(time.perf_counter() - begin)
        for query in FUZZY_QUERY_SET:
            begin = time.perf_counter()
            service.find_image(query)
            fuzzy_times.append(time.perf_counter() - begin)

    negative_rows = _run_negative_invariants(service)
    violations = [row for row in negative_rows if row["violated"]]
    negative_invariant_violations = sum(1 for row in negative_rows if row["violated"])

    logical_summary = _logical_association_summary(assets)
    metrics["negative_invariant_violations"] = negative_invariant_violations
    metrics["duplicate_logical_associations"] = logical_summary["duplicate_logical_associations"]
    metrics["logical_associations_total"] = logical_summary["logical_associations_total"]
    metrics["unique_logical_associations"] = logical_summary["unique_logical_associations"]
    audit_data["negative_invariant_evidence"] = negative_rows
    audit_data["duplicate_logical_evidence"] = logical_summary
    _validate_audit_schema(audit_data)
    if metrics["negative_invariant_violations"] != sum(
        1 for row in audit_data["negative_invariant_evidence"] if row["violated"]
    ):
        raise AssertionError("negative invariant metric does not match evidence")
    _write_json(artifact / "library-audit.json", audit_data)

    _write_json(
        artifact / "find-image-results.json",
        {
            "queries": exact_rows,
            "fuzzy_queries": fuzzy_rows,
            "negative_cases": negative_rows,
            "negative_invariant_violations": violations,
        },
    )

    performance = {
        "index_load_seconds": round(index_load_seconds, 6),
        "exact_lookup": _timing(exact_times),
        "fuzzy_lookup": _timing(fuzzy_times),
        "audit_seconds": round(audit_seconds, 6),
        "canonical_assets": len(assets),
        "exact_duplicate_observations": int(metrics.get("exact_duplicate_observations", 0)),
        "near_duplicate_variants": int(metrics.get("near_duplicate_variants", 0)),
    }
    for filename, key in (
        ("ingest-seconds.txt", "ingest_seconds"),
        ("standalone-ingest-seconds.txt", "standalone_ingest_seconds"),
        ("second-ingest-seconds.txt", "incremental_seconds"),
    ):
        path = artifact / filename
        performance[key] = int(path.read_text(encoding="utf-8").strip()) if path.is_file() else None
    _write_json(artifact / "performance.json", performance)

    review_groups = build_review_dataset(
        library,
        priority_rows=priority.rows,
        max_products=args.review_limit,
        candidates_per_product=4,
    )
    review_dir = artifact / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_manifest = dataset_payload(review_groups)
    _write_json(review_dir / "review-dataset.json", review_manifest)
    render_contact_sheet(review_groups, review_dir / "review-contact-sheet.png", candidates_per_row=4)
    (artifact / "review-files.txt").write_text(
        "\n".join(str(path) for path in sorted(review_dir.rglob("*")) if path.is_file()),
        encoding="utf-8",
    )

    structured = {
        "files_seen": priority.files_seen,
        "exact_documents": priority.exact_documents,
        "logical_documents": priority.logical_documents,
        "product_occurrences": priority.product_occurrences,
        "unique_products": priority.unique_products,
        "known_phase2_unique_products_baseline_approx": 914,
        "delta_from_approx_baseline": priority.unique_products - 914,
        "warnings": list(priority.warnings),
    }
    _write_json(artifact / "structured-corpus-coverage.json", structured)

    gates = {
        "audit_generated": (artifact / "library-audit.json").is_file(),
        "catalog_520": total == 520,
        "department_catalog_520": int(departments.get("catalog_products", 0)) == 520,
        "top_missing_generated": top_missing_path.is_file(),
        "find_image_identity_invariants": not violations,
        "performance_measured": bool(exact_times and fuzzy_times),
        "review_dataset_generated": (review_dir / "review-dataset.json").is_file(),
        "review_contact_sheet_generated": (review_dir / "review-contact-sheet.png").is_file(),
        "structured_priority_generated": priority.unique_products > 0,
    }
    _write_json(artifact / "operational-analysis-gates.json", gates)
    return 0 if all(gates.values()) else 13


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run corpus-dependent Image DB Phase 3 audit/coverage/query/performance gates.")
    parser.add_argument("--library", required=True)
    parser.add_argument("--product-db", required=True)
    parser.add_argument("--corpus-source", action="append", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--review-limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
