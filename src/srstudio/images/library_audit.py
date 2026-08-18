from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from srstudio.images.association import normalize_product_name
from srstudio.images.lookup import ProductImageLookupService
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


@dataclass(frozen=True, slots=True)
class LibraryAudit:
    metrics: LibraryAuditMetrics
    products_without_image: tuple[str, ...]
    pending_product_names: tuple[str, ...]
    review_reasons: tuple[tuple[str, int], ...]
    source_kinds: tuple[tuple[str, int], ...]
    queries: tuple[dict, ...] = ()


def audit_library(library, catalog_names: Iterable[str] = (), queries: Iterable[str] = ()) -> LibraryAudit:
    assets = list(library.all())
    catalog = _catalog_map(catalog_names)
    accepted_names: set[str] = set()
    pending_names: set[str] = set()
    raw_observations = 0
    variant_hashes = 0
    review_reasons: Counter[str] = Counter()
    source_kinds: Counter[str] = Counter()

    accepted_assets = pending_assets = rejected_assets = 0
    product_assets = decorative_assets = unknown_assets = 0
    preferred_assets = images_without_product = 0

    for asset in assets:
        metadata = dict(getattr(asset, "metadata", {}) or {})
        kind = str(getattr(asset, "kind", "") or "").lower()
        status = str(getattr(asset, "review_status", "") or "").lower()
        product_name = str(getattr(asset, "product_key", "") or getattr(asset, "product_name", "") or "")
        aliases = tuple(getattr(asset, "aliases", ()) or ())
        normalized_names = {
            normalized
            for value in (product_name, *aliases)
            if (normalized := normalize_product_name(str(value)))
        }

        provenance = metadata.get("provenance")
        if isinstance(provenance, dict):
            provenance_rows = [provenance]
        elif isinstance(provenance, (list, tuple)):
            provenance_rows = [row for row in provenance if isinstance(row, dict)]
        else:
            provenance_rows = []
        raw_observations += max(1, len(provenance_rows))
        variant_hashes += len({str(value) for value in metadata.get("variant_sha256", ()) if value})

        for row in provenance_rows:
            source_kind = str(row.get("source_kind", "") or "")
            if source_kind:
                source_kinds[source_kind] += 1
        if not provenance_rows:
            source = str(getattr(asset, "source", "") or "")
            if source:
                source_kinds[source] += 1

        if kind == "product":
            product_assets += 1
            if not normalized_names:
                images_without_product += 1
        elif kind == "decorative" or metadata.get("association_status") == "decorative":
            decorative_assets += 1
        else:
            unknown_assets += 1

        if status == "accepted":
            accepted_assets += 1
            accepted_names.update(normalized_names)
        elif status in {"rejected", "reject"}:
            rejected_assets += 1
        else:
            pending_assets += 1
            pending_names.update(normalized_names)
            reason = str(metadata.get("review_reason") or metadata.get("match_reason") or "unspecified")
            review_reasons[reason] += 1

        if bool(getattr(asset, "preferred", False)):
            preferred_assets += 1

    covered_catalog = set(catalog) & accepted_names
    missing_catalog = sorted(set(catalog) - covered_catalog)
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
            accepted_products=len(accepted_names),
            pending_products=len(pending_names),
            catalog_products=len(catalog),
            catalog_products_with_accepted_image=len(covered_catalog),
            catalog_products_without_accepted_image=len(missing_catalog),
        ),
        products_without_image=tuple(catalog[name] for name in missing_catalog),
        pending_product_names=tuple(sorted(pending_names)),
        review_reasons=tuple(review_reasons.most_common()),
        source_kinds=tuple(source_kinds.most_common()),
        queries=query_rows,
    )


def _catalog_map(names: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in names:
        display = " ".join(str(value or "").split())
        normalized = normalize_product_name(display)
        if display and normalized:
            result.setdefault(normalized, display)
    return result


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
            "best_image_id": str(getattr(best, "id", "")) if best is not None else "",
            "best_product_name": str(getattr(best, "product_name", "")) if best is not None else "",
            "alternatives": [
                {
                    "image_id": str(getattr(asset, "id", "")),
                    "product_name": str(getattr(asset, "product_name", "")),
                }
                for asset in result.alternatives
            ],
        }


def payload(audit: LibraryAudit) -> dict:
    return {
        "metrics": asdict(audit.metrics),
        "products_without_image": list(audit.products_without_image),
        "pending_product_names": list(audit.pending_product_names),
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
    parser.add_argument("--query", action="append", default=[])
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
    audit = audit_library(SafeImageLibrary(args.library), catalog, args.query)
    data = payload(audit)
    if warnings:
        data["warnings"] = warnings
    if args.report:
        data["report_path"] = str(write_report(args.report, data))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
