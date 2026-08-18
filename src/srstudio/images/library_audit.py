from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from srstudio.images.association import normalize_product_name
from srstudio.images.lookup import ProductImageLookupService
from srstudio.images.product_priority import ProductPriorityRow, scan_product_priority
from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_cli import catalog_names_from_sqlite


@dataclass(frozen=True, slots=True)
class LibraryAuditMetrics:
    canonical_assets: int
    raw_observations: int
    visual_variant_hashes: int
    product_assets: int
    accepted_assets: int
    pending_assets: int
    rejected_assets: int
    preferred_assets: int
    decorative_assets: int
    unknown_assets: int
    images_without_product: int
    accepted_products: int
    pending_products: int
    catalog_products: int
    catalog_products_with_accepted_image: int
    catalog_products_without_accepted_image: int
    physical_images: int = 0
    exact_duplicate_observations: int = 0
    near_duplicate_variants: int = 0
    likely_assets: int = 0
    review_required_assets: int = 0
    likely_products: int = 0
    review_required_products: int = 0
    products_with_multiple_images: int = 0
    associations_without_provenance: int = 0
    low_confidence_associations: int = 0
    catalog_auto_approved: int = 0
    catalog_likely: int = 0
    catalog_review_required: int = 0
    catalog_without_any_image: int = 0


@dataclass(frozen=True, slots=True)
class LibraryAudit:
    metrics: LibraryAuditMetrics
    products_without_image: tuple[str, ...]
    pending_product_names: tuple[str, ...]
    review_reasons: tuple[tuple[str, int], ...]
    source_kinds: tuple[tuple[str, int], ...]
    queries: tuple[dict, ...] = ()
    products_without_any_image: tuple[str, ...] = ()
    products_with_multiple_images: tuple[tuple[str, int], ...] = ()
    priority_missing: tuple[dict, ...] = ()


def audit_library(
    library,
    catalog_names: Iterable[str] = (),
    queries: Iterable[str] = (),
    *,
    priority_rows: Iterable[ProductPriorityRow | dict] = (),
    low_confidence_threshold: float = 0.80,
    top_missing_limit: int = 100,
) -> LibraryAudit:
    """Audit coverage/review state without loading image pixels.

    `products_without_image` retains the historical meaning "without an accepted
    image" for compatibility. `products_without_any_image` is the Phase-2 metric:
    no accepted, likely or review-required usable candidate exists.
    """
    assets = list(library.all())
    catalog = _catalog_map(catalog_names)

    accepted_canonical: set[str] = set()
    pending_canonical: set[str] = set()
    likely_canonical: set[str] = set()
    review_canonical: set[str] = set()
    accepted_search: set[str] = set()
    likely_search: set[str] = set()
    review_search: set[str] = set()
    product_asset_counts: Counter[str] = Counter()

    raw_observations = 0
    exact_duplicate_observations = 0
    variant_hashes = 0
    review_reasons: Counter[str] = Counter()
    source_kinds: Counter[str] = Counter()

    accepted_assets = pending_assets = rejected_assets = 0
    likely_assets = review_required_assets = 0
    product_assets = decorative_assets = unknown_assets = 0
    preferred_assets = images_without_product = 0
    physical_images = associations_without_provenance = low_confidence_associations = 0

    for asset in assets:
        metadata = dict(getattr(asset, "metadata", {}) or {})
        kind = str(getattr(asset, "kind", "") or "").lower()
        status = str(getattr(asset, "review_status", "") or "").lower()
        association_status = str(metadata.get("association_status", "") or "").lower()
        canonical_display = str(
            getattr(asset, "product_key", "")
            or getattr(asset, "product_name", "")
            or ""
        )
        canonical_name = normalize_product_name(canonical_display)
        aliases = tuple(getattr(asset, "aliases", ()) or ())
        alias_names = {
            normalized
            for value in aliases
            if (normalized := normalize_product_name(str(value)))
        }
        search_names = ({canonical_name} if canonical_name else set()) | alias_names

        path = str(getattr(asset, "path", "") or "")
        if path and Path(path).is_file():
            physical_images += 1

        provenance_rows = _combined_provenance(metadata)
        raw_observations += max(1, len(provenance_rows))
        exact_duplicate_observations += max(0, len(provenance_rows) - 1)
        variants = {str(value) for value in metadata.get("variant_sha256", ()) if value}
        variant_hashes += len(variants)

        for row in provenance_rows:
            source_kind = str(row.get("source_kind", "") or "")
            if source_kind:
                source_kinds[source_kind] += 1
        if not provenance_rows:
            source = str(getattr(asset, "source", "") or "")
            if source:
                source_kinds[source] += 1

        is_decorative = kind == "decorative" or association_status == "decorative"
        is_product = not is_decorative and (kind == "product" or bool(canonical_name))
        if is_decorative:
            decorative_assets += 1
        elif is_product:
            product_assets += 1
            if canonical_name:
                product_asset_counts[canonical_name] += 1
        else:
            unknown_assets += 1

        if not is_decorative and not canonical_name:
            images_without_product += 1

        if is_product and canonical_name:
            source_file = str(getattr(asset, "source_file", "") or "")
            source = str(getattr(asset, "source", "") or "")
            if not provenance_rows and not source_file and not source:
                associations_without_provenance += 1
            try:
                confidence = float(getattr(asset, "confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if status not in {"rejected", "reject"} and confidence < float(low_confidence_threshold):
                low_confidence_associations += 1

        if status == "accepted":
            accepted_assets += 1
            if canonical_name:
                accepted_canonical.add(canonical_name)
                accepted_search.update(search_names)
        elif status in {"rejected", "reject"}:
            rejected_assets += 1
        else:
            pending_assets += 1
            if canonical_name:
                pending_canonical.add(canonical_name)
            if association_status in {"probable", "likely"}:
                likely_assets += 1
                if canonical_name:
                    likely_canonical.add(canonical_name)
                    likely_search.update(search_names)
            else:
                review_required_assets += 1
                if canonical_name:
                    review_canonical.add(canonical_name)
                    review_search.update(search_names)
            reason = str(metadata.get("review_reason") or metadata.get("match_reason") or association_status or "unspecified")
            review_reasons[reason] += 1

        if bool(getattr(asset, "preferred", False)):
            preferred_assets += 1

    # Accepted wins over lower states; likely wins over generic review.
    likely_search -= accepted_search
    review_search -= accepted_search | likely_search
    likely_canonical -= accepted_canonical
    review_canonical -= accepted_canonical | likely_canonical

    covered_catalog = set(catalog) & accepted_search
    likely_catalog = (set(catalog) & likely_search) - covered_catalog
    review_catalog = (set(catalog) & review_search) - covered_catalog - likely_catalog
    usable_catalog = covered_catalog | likely_catalog | review_catalog
    missing_accepted = sorted(set(catalog) - covered_catalog)
    missing_any = sorted(set(catalog) - usable_catalog)

    multiple = tuple(sorted(
        ((name, count) for name, count in product_asset_counts.items() if count > 1),
        key=lambda item: (-item[1], item[0]),
    ))
    priority_missing = _priority_missing_rows(
        priority_rows,
        usable_names=accepted_search | likely_search | review_search,
        catalog=catalog,
        limit=top_missing_limit,
    )
    query_rows = tuple(_audit_queries(library, queries))

    return LibraryAudit(
        metrics=LibraryAuditMetrics(
            canonical_assets=len(assets),
            raw_observations=raw_observations,
            visual_variant_hashes=variant_hashes,
            product_assets=product_assets,
            accepted_assets=accepted_assets,
            pending_assets=pending_assets,
            rejected_assets=rejected_assets,
            preferred_assets=preferred_assets,
            decorative_assets=decorative_assets,
            unknown_assets=unknown_assets,
            images_without_product=images_without_product,
            accepted_products=len(accepted_canonical),
            pending_products=len(pending_canonical),
            catalog_products=len(catalog),
            catalog_products_with_accepted_image=len(covered_catalog),
            catalog_products_without_accepted_image=len(missing_accepted),
            physical_images=physical_images,
            exact_duplicate_observations=exact_duplicate_observations,
            near_duplicate_variants=variant_hashes,
            likely_assets=likely_assets,
            review_required_assets=review_required_assets,
            likely_products=len(likely_canonical),
            review_required_products=len(review_canonical),
            products_with_multiple_images=len(multiple),
            associations_without_provenance=associations_without_provenance,
            low_confidence_associations=low_confidence_associations,
            catalog_auto_approved=len(covered_catalog),
            catalog_likely=len(likely_catalog),
            catalog_review_required=len(review_catalog),
            catalog_without_any_image=len(missing_any),
        ),
        products_without_image=tuple(catalog[name] for name in missing_accepted),
        pending_product_names=tuple(sorted(pending_canonical)),
        review_reasons=tuple(review_reasons.most_common()),
        source_kinds=tuple(source_kinds.most_common()),
        queries=query_rows,
        products_without_any_image=tuple(catalog[name] for name in missing_any),
        products_with_multiple_images=multiple,
        priority_missing=priority_missing,
    )


def _combined_provenance(metadata: dict) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for value in (metadata.get("provenance"), metadata.get("source_provenance")):
        if isinstance(value, dict):
            rows = (value,)
        elif isinstance(value, (list, tuple)):
            rows = value
        else:
            rows = ()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(dict(row))
    return result


def _catalog_map(names: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in names:
        display = " ".join(str(value or "").split())
        normalized = normalize_product_name(display)
        if display and normalized:
            result.setdefault(normalized, display)
    return result


def _priority_missing_rows(
    rows: Iterable[ProductPriorityRow | dict],
    *,
    usable_names: set[str],
    catalog: dict[str, str],
    limit: int,
) -> tuple[dict, ...]:
    result: list[dict] = []
    for row in rows:
        if isinstance(row, ProductPriorityRow):
            data = asdict(row)
        elif isinstance(row, dict):
            data = dict(row)
        else:
            continue
        normalized = normalize_product_name(str(data.get("normalized_name") or data.get("display_name") or ""))
        if not normalized or normalized in usable_names:
            continue
        data["normalized_name"] = normalized
        data["display_name"] = catalog.get(normalized, str(data.get("display_name") or normalized))
        data["catalog_present"] = normalized in catalog or bool(data.get("catalog_present"))
        data["coverage_status"] = "missing"
        result.append(data)
    result.sort(
        key=lambda data: (
            float(data.get("priority_score", 0.0) or 0.0),
            int(data.get("occurrence_count", 0) or 0),
            int(data.get("source_count", 0) or 0),
        ),
        reverse=True,
    )
    return tuple(result[: max(0, int(limit))])


def _audit_queries(library, queries: Iterable[str]):
    service = ProductImageLookupService(library)
    service.refresh()
    for query in queries:
        value = " ".join(str(query or "").split())
        if not value:
            continue
        result = service.find_image(value)
        best = result.best_match
        yield {
            "query": value,
            "found": best is not None,
            "confidence": float(result.confidence),
            "match_type": result.match_type,
            "quality_score": result.quality_score,
            "best_image_id": str(getattr(best.asset, "id", "")) if best is not None else "",
            "best_product_name": str(getattr(best.asset, "product_name", "")) if best is not None else "",
            "provenance": list(result.provenance),
            "alternatives": [
                {
                    "image_id": str(getattr(candidate.asset, "id", "")),
                    "product_name": str(getattr(candidate.asset, "product_name", "")),
                    "confidence": candidate.score,
                    "quality_score": candidate.quality_score,
                }
                for candidate in result.alternatives
            ],
        }


def coverage_payload(metrics: LibraryAuditMetrics) -> dict:
    total = metrics.catalog_products
    denominator = max(1, total)
    return {
        "catalog_products": total,
        "auto_approved": metrics.catalog_auto_approved,
        "auto_approved_percent": round(100.0 * metrics.catalog_auto_approved / denominator, 2) if total else 0.0,
        "likely": metrics.catalog_likely,
        "likely_percent": round(100.0 * metrics.catalog_likely / denominator, 2) if total else 0.0,
        "review_required": metrics.catalog_review_required,
        "review_required_percent": round(100.0 * metrics.catalog_review_required / denominator, 2) if total else 0.0,
        "without_any_image": metrics.catalog_without_any_image,
        "without_any_image_percent": round(100.0 * metrics.catalog_without_any_image / denominator, 2) if total else 0.0,
    }


def payload(audit: LibraryAudit) -> dict:
    return {
        "metrics": asdict(audit.metrics),
        "coverage": coverage_payload(audit.metrics),
        "products_without_image": list(audit.products_without_image),
        "products_without_any_image": list(audit.products_without_any_image),
        "pending_product_names": list(audit.pending_product_names),
        "products_with_multiple_images": [
            {"product_name": name, "image_count": count}
            for name, count in audit.products_with_multiple_images
        ],
        "priority_missing": list(audit.priority_missing),
        "review_reasons": [
            {"reason": reason, "count": count}
            for reason, count in audit.review_reasons
        ],
        "source_kinds": [
            {"source_kind": source_kind, "count": count}
            for source_kind, count in audit.source_kinds
        ],
        "queries": list(audit.queries),
    }


def write_report(path: str | Path, data: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(target)
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audita cobertura e fila de revisão do banco Produto↔Imagem.")
    parser.add_argument("--library", required=True)
    parser.add_argument("--product-db", default=None)
    parser.add_argument("--catalog-name", action="append", default=[])
    parser.add_argument("--corpus-source", action="append", default=[], help="PPTX/ZIP para ranking Top Missing")
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--top-missing-limit", type=int, default=100)
    parser.add_argument("--report", default=None)
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

    priority_rows: Iterable[ProductPriorityRow] = ()
    priority_payload: dict[str, Any] | None = None
    if args.corpus_source:
        priority_report = scan_product_priority(args.corpus_source, catalog_names=catalog)
        priority_rows = priority_report.rows
        warnings.extend(priority_report.warnings)
        priority_payload = {
            "files_seen": priority_report.files_seen,
            "exact_documents": priority_report.exact_documents,
            "logical_documents": priority_report.logical_documents,
            "product_occurrences": priority_report.product_occurrences,
            "unique_products": priority_report.unique_products,
        }

    audit = audit_library(
        SafeImageLibrary(args.library),
        catalog,
        args.query,
        priority_rows=priority_rows,
        top_missing_limit=args.top_missing_limit,
    )
    data = payload(audit)
    if priority_payload is not None:
        data["priority_corpus"] = priority_payload
    if warnings:
        data["warnings"] = list(dict.fromkeys(warnings))
    if args.report:
        data["report_path"] = str(write_report(args.report, data))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
