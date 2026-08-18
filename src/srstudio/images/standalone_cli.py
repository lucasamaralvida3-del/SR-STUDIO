from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_state import (
    STANDALONE_STATE_VERSION,
    StandaloneStateStore,
    catalog_fingerprint,
    standalone_source_fingerprint,
)
from srstudio.images.standalone_training import (
    StandaloneImageSource,
    StandaloneProductImageTrainer,
    load_manifest,
)


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_NAME_COLUMNS = ("display_name", "name", "product_name", "ultimo_nome", "descricao", "description")
_PRODUCT_TABLES = ("products", "produtos", "product", "catalog", "catalogo")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def discover_images(sources: Iterable[str | Path]) -> tuple[list[StandaloneImageSource], list[str]]:
    """Discover standalone raster assets without inventing product labels."""
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


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsafe SQLite identifier: {value!r}")
    return f'"{value}"'


def catalog_names_from_sqlite(path: str | Path) -> list[str]:
    """Read product names from a known catalog table in strict read-only mode.

    Supports the SR Studio `products` schema and the real historical atacado
    `produtos` schema, plus a small explicit allow-list of legacy catalog table
    names. The selected table and columns are discovered from SQLite metadata,
    quoted defensively, and never created or modified. Empty preferred name
    columns fall through to the next supported column such as `ultimo_nome`.
    """
    database = Path(path)
    if not database.is_file():
        raise FileNotFoundError(database)
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        actual_tables = {str(row[0]).lower(): str(row[0]) for row in table_rows if row and row[0]}
        table_name = next(
            (actual_tables[candidate] for candidate in _PRODUCT_TABLES if candidate in actual_tables),
            None,
        )
        if table_name is None:
            raise ValueError(
                "product catalog table not found; expected one of: " + ", ".join(_PRODUCT_TABLES)
            )

        quoted_table = _quote_identifier(table_name)
        columns = [
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        ]
        if not columns:
            raise ValueError(f"{table_name} table has no columns")
        lower_map = {column.lower(): column for column in columns}
        selected = [lower_map[name] for name in _NAME_COLUMNS if name in lower_map]
        if not selected:
            raise ValueError(f"{table_name} table has no supported product-name column")
        identifiers = [_quote_identifier(column) for column in selected]
        nullable = [f"NULLIF(TRIM({identifier}), '')" for identifier in identifiers]
        expression = "COALESCE(" + ", ".join(nullable) + ", '')"
        rows = connection.execute(
            f"SELECT {expression} FROM {quoted_table} WHERE {expression} <> ''"
        ).fetchall()

    result: list[str] = []
    seen: set[str] = set()
    for (raw_value,) in rows:
        value = " ".join(str(raw_value or "").split())
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


def run_incremental_standalone(
    library,
    sources: Iterable[StandaloneImageSource],
    catalog: Iterable[str],
    *,
    state_path: str | Path,
    force: bool = False,
):
    """Process only changed standalone source+mapping+catalog inputs.

    A record is skipped only when its fingerprint is unchanged and, for imported
    candidates, the referenced canonical image still exists. Thus a valid
    library restore/prune cannot leave stale state silently hiding a missing asset.
    """
    source_rows = list(sources)
    catalog_rows = list(catalog)
    store = StandaloneStateStore(state_path)
    state = store.load()
    records = state.setdefault("records", {})
    catalog_digest = catalog_fingerprint(catalog_rows)

    pending: list[StandaloneImageSource] = []
    fingerprints: dict[str, str] = {}
    skipped = 0
    library_ids: set[str] | None = None

    for source in source_rows:
        path = Path(source.path)
        if not path.is_file():
            pending.append(source)
            continue
        key = str(path.resolve())
        fingerprint = standalone_source_fingerprint(source, catalog_digest)
        fingerprints[key] = fingerprint
        record = records.get(key)
        if not force and isinstance(record, dict) and record.get("fingerprint") == fingerprint:
            status = str(record.get("status") or "")
            image_id = str(record.get("image_id") or "")
            if status == "unknown":
                skipped += 1
                continue
            if image_id:
                if library_ids is None:
                    library_ids = {str(asset.id) for asset in library.all()}
                if image_id in library_ids:
                    skipped += 1
                    continue
            # accepted/review records without a live canonical image are stale
            # relative to the library and intentionally fall through.
        pending.append(source)

    report = StandaloneProductImageTrainer(library, catalog_rows).train(pending)
    for match in report.matches:
        path = Path(match.path)
        if not path.is_file():
            continue
        key = str(path.resolve())
        fingerprint = fingerprints.get(key)
        if not fingerprint:
            continue
        records[key] = {
            "fingerprint": fingerprint,
            "status": match.status,
            "reason": match.reason,
            "product_name": match.product_name,
            "image_id": match.image_id,
        }

    state["version"] = STANDALONE_STATE_VERSION
    state["catalog_sha256"] = catalog_digest
    store.save(state)
    return report, skipped, len(source_rows)


def report_payload(
    report,
    *,
    discovery_warnings: Iterable[str] = (),
    skipped: int = 0,
    discovered_total: int | None = None,
) -> dict:
    return {
        "metrics": {
            "discovered": report.discovered if discovered_total is None else int(discovered_total),
            "processed": report.discovered,
            "skipped": int(skipped),
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
        description="Ingere fotos de produto isoladas com matching conservador e incremental contra o catálogo."
    )
    parser.add_argument("sources", nargs="*", help="Imagens ou diretórios de imagens")
    parser.add_argument("--library", required=True, help="Diretório persistente do banco de imagens")
    parser.add_argument("--product-db", default=None, help="SQLite de produtos existente, aberto somente para leitura")
    parser.add_argument("--catalog-name", action="append", default=[], help="Nome adicional de produto do catálogo")
    parser.add_argument("--manifest", default=None, help="JSON com mappings explícitos/validados")
    parser.add_argument("--state", default=None, help="Estado incremental; padrão <library>/standalone_state.json")
    parser.add_argument("--force", action="store_true", help="Reprocessa todas as fontes standalone desta execução")
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
    state_path = args.state or str(Path(args.library) / "standalone_state.json")
    report, skipped, discovered_total = run_incremental_standalone(
        library,
        sources,
        catalog,
        state_path=state_path,
        force=args.force,
    )
    output = report_payload(
        report,
        discovery_warnings=warnings,
        skipped=skipped,
        discovered_total=discovered_total,
    )
    output["state_path"] = str(state_path)
    if args.report:
        output["report_path"] = str(write_report(args.report, output))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
