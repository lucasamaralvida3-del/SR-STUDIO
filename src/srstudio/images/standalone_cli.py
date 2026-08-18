from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_training import (
    StandaloneImageSource,
    StandaloneProductImageTrainer,
    load_manifest,
)


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def discover_images(sources: Iterable[str | Path]) -> tuple[list[StandaloneImageSource], list[str]]:
    """Discover standalone raster assets without inventing product labels.

    The filename is deliberately left as implicit evidence inside the trainer. A
    numeric/opaque filename therefore remains unknown instead of being auto-linked.
    """
    rows: list[StandaloneImageSource] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for item in sources:
        path = Path(item)
        candidates: list[Path]
        if path.is_dir():
            candidates = sorted(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in _IMAGE_SUFFIXES
            )
        elif path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
            candidates = [path]
        else:
            warnings.append(f"Unsupported or missing standalone source: {path}")
            continue
        for candidate in candidates:
            key = str(candidate.resolve())
            if key in seen:
                continue
            seen.add(key)
            rows.append(StandaloneImageSource(path=str(candidate)))
    return rows, warnings


def catalog_names_from_sqlite(path: str | Path) -> list[str]:
    """Read product names from the existing product DB without mutating its schema."""
    database = Path(path)
    if not database.is_file():
        raise FileNotFoundError(database)
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT name, display_name FROM products WHERE COALESCE(name, '') <> '' OR COALESCE(display_name, '') <> ''"
        ).fetchall()
    result: list[str] = []
    seen: set[str] = set()
    for name, display_name in rows:
        value = " ".join(str(display_name or name or "").split())
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def merge_sources(
    discovered: Iterable[StandaloneImageSource],
    manifest_rows: Iterable[StandaloneImageSource],
) -> list[StandaloneImageSource]:
    """Prefer manifest evidence for a file and keep directory discovery as fallback."""
    by_path: dict[str, StandaloneImageSource] = {}
    for row in discovered:
        by_path[str(Path(row.path).resolve())] = row
    for row in manifest_rows:
        by_path[str(Path(row.path).resolve())] = row
    return list(by_path.values())


def report_payload(report, *, discovery_warnings: Iterable[str] = ()) -> dict:
    return {
        "metrics": {
            "discovered": report.discovered,
            "accepted": report.accepted,
            "review": report.review,
            "unknown": report.unknown,
            "imported": report.imported,
        },
        "matches": [asdict(item) for item in report.matches],
        "warnings": list(dict.fromkeys([*discovery_warnings, *report.warnings])),
    }


def write_report(path: str | Path, payload: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(target)
    return target


def _resolve_manifest_rows(manifest_path: str | Path) -> list[StandaloneImageSource]:
    manifest = Path(manifest_path)
    rows = load_manifest(manifest)
    resolved: list[StandaloneImageSource] = []
    for row in rows:
        image_path = Path(row.path)
        if not image_path.is_absolute():
            image_path = manifest.parent / image_path
        resolved.append(
            StandaloneImageSource(
                path=str(image_path),
                label=row.label,
                product_name=row.product_name,
                verified=row.verified,
                provenance=row.provenance,
            )
        )
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingere fotos de produto isoladas com matching conservador contra o catálogo."
    )
    parser.add_argument("sources", nargs="*", help="Imagens ou diretórios de imagens")
    parser.add_argument("--library", required=True, help="Diretório persistente do banco de imagens")
    parser.add_argument("--product-db", default=None, help="SQLite products.db existente, aberto somente para leitura")
    parser.add_argument("--catalog-name", action="append", default=[], help="Nome adicional de produto do catálogo")
    parser.add_argument("--manifest", default=None, help="JSON com mappings explícitos/validados")
    parser.add_argument("--report", default=None, help="Grava relatório JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    discovered, warnings = discover_images(args.sources)
    manifest_rows = _resolve_manifest_rows(args.manifest) if args.manifest else []
    sources = merge_sources(discovered, manifest_rows)

    catalog = list(args.catalog_name)
    if args.product_db:
        try:
            catalog.extend(catalog_names_from_sqlite(args.product_db))
        except Exception as exc:
            warnings.append(f"Product database could not be read: {args.product_db}: {exc}")

    library = SafeImageLibrary(args.library)
    report = StandaloneProductImageTrainer(library, catalog).train(sources)
    payload = report_payload(report, discovery_warnings=warnings)
    if args.report:
        payload["report_path"] = str(write_report(args.report, payload))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
