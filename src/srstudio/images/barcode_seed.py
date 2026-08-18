from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Protocol


_BARCODE_COLUMNS = (
    "barcode",
    "ean",
    "ean13",
    "gtin",
    "gtin13",
    "codigo_barras",
    "cod_barras",
    "codbarras",
    "bar_code",
)
_NAME_COLUMNS = ("display_name", "name", "product_name", "descricao", "description")
_CODE_RE = re.compile(r"\d{8,14}")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class BarcodeProvider(Protocol):
    def available(self) -> bool: ...

    def read(self, image_path: str | Path) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class BarcodeCatalogEntry:
    barcode: str
    product_name: str


@dataclass(frozen=True, slots=True)
class BarcodeResolution:
    path: str
    barcodes: tuple[str, ...]
    product_name: str = ""
    status: str = "unknown"
    reason: str = ""


@dataclass(slots=True)
class BarcodeSeedReport:
    files: int = 0
    resolved: int = 0
    review: int = 0
    unknown: int = 0
    resolutions: list[BarcodeResolution] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ZBarImgProvider:
    """Optional zbarimg CLI adapter; no Python barcode package is required."""

    def __init__(self, executable: str = "zbarimg", timeout_seconds: int = 30) -> None:
        self.executable = executable
        self.timeout_seconds = int(timeout_seconds)

    def available(self) -> bool:
        return bool(shutil.which(self.executable))

    def read(self, image_path: str | Path) -> list[str]:
        if not self.available():
            raise RuntimeError(f"Barcode executable not available: {self.executable}")
        completed = subprocess.run(
            [self.executable, "--quiet", "--raw", str(image_path)],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode not in {0, 4}:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"zbarimg failed ({completed.returncode}): {detail[:500]}")
        result: list[str] = []
        seen: set[str] = set()
        for line in completed.stdout.splitlines():
            code = normalize_barcode(line)
            if code and code not in seen:
                seen.add(code)
                result.append(code)
        return result


def normalize_barcode(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8 or len(digits) > 14:
        return ""
    return digits


def discover_barcode_catalog(database_path: str | Path) -> tuple[list[BarcodeCatalogEntry], list[str]]:
    """Read an existing product database in mode=ro and discover barcode/name columns."""
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    warnings: list[str] = []
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(products)").fetchall()]
        lower_map = {column.lower(): column for column in columns}
        barcode_column = next((lower_map[name] for name in _BARCODE_COLUMNS if name in lower_map), "")
        name_column = next((lower_map[name] for name in _NAME_COLUMNS if name in lower_map), "")
        if not barcode_column:
            warnings.append("No supported barcode/EAN/GTIN column found in products table")
            return [], warnings
        if not name_column:
            warnings.append("No supported product-name column found in products table")
            return [], warnings
        rows = connection.execute(
            f'SELECT "{barcode_column}", "{name_column}" FROM products '
            f'WHERE COALESCE("{barcode_column}", "") <> ""'
        ).fetchall()

    entries: list[BarcodeCatalogEntry] = []
    seen: set[tuple[str, str]] = set()
    for barcode, product_name in rows:
        code = normalize_barcode(str(barcode or ""))
        name = " ".join(str(product_name or "").split())
        key = (code, name)
        if code and name and key not in seen:
            seen.add(key)
            entries.append(BarcodeCatalogEntry(code, name))
    return entries, warnings


class BarcodeSeedResolver:
    """Create verified standalone mappings only for unambiguous exact barcode hits."""

    def __init__(self, provider: BarcodeProvider, catalog: Iterable[BarcodeCatalogEntry]) -> None:
        self.provider = provider
        self.by_barcode: dict[str, set[str]] = {}
        for entry in catalog:
            self.by_barcode.setdefault(entry.barcode, set()).add(entry.product_name)

    def resolve(self, sources: Iterable[str | Path]) -> BarcodeSeedReport:
        report = BarcodeSeedReport()
        paths = list(_discover_images(sources, report.warnings))
        report.files = len(paths)

        if not self.provider.available():
            report.unknown = len(paths)
            report.warnings.append("Barcode provider unavailable")
            report.resolutions.extend(
                BarcodeResolution(str(path), (), status="unknown", reason="provider-unavailable")
                for path in paths
            )
            return report

        for path in paths:
            try:
                codes = tuple(dict.fromkeys(normalize_barcode(code) for code in self.provider.read(path) if normalize_barcode(code)))
            except Exception as exc:
                report.unknown += 1
                report.warnings.append(f"{path}: barcode read failed: {exc}")
                report.resolutions.append(
                    BarcodeResolution(str(path), (), status="unknown", reason="read-failed")
                )
                continue

            matched_names: set[str] = set()
            for code in codes:
                matched_names.update(self.by_barcode.get(code, set()))

            if len(codes) == 1 and len(matched_names) == 1:
                product_name = next(iter(matched_names))
                report.resolved += 1
                report.resolutions.append(
                    BarcodeResolution(
                        str(path), codes, product_name, "resolved", "exact-barcode-catalog-match"
                    )
                )
            elif matched_names:
                report.review += 1
                report.resolutions.append(
                    BarcodeResolution(
                        str(path), codes, status="review", reason="ambiguous-barcode-match"
                    )
                )
            else:
                report.unknown += 1
                report.resolutions.append(
                    BarcodeResolution(
                        str(path), codes, status="unknown", reason="barcode-not-in-catalog" if codes else "barcode-not-found"
                    )
                )
        return report


def manifest_payload(report: BarcodeSeedReport) -> dict:
    images = []
    for row in report.resolutions:
        if row.status != "resolved" or not row.product_name or len(row.barcodes) != 1:
            continue
        images.append(
            {
                "path": row.path,
                "product_name": row.product_name,
                "verified": True,
                "provenance": {
                    "match_method": "exact-barcode-catalog-match",
                    "barcode": row.barcodes[0],
                },
            }
        )
    return {"images": images}


def report_payload(report: BarcodeSeedReport) -> dict:
    return {
        "metrics": {
            "files": report.files,
            "resolved": report.resolved,
            "review": report.review,
            "unknown": report.unknown,
        },
        "resolutions": [asdict(row) for row in report.resolutions],
        "warnings": list(dict.fromkeys(report.warnings)),
    }


def write_json(path: str | Path, payload: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(target)
    return target


def _discover_images(sources: Iterable[str | Path], warnings: list[str]):
    seen: set[str] = set()
    for item in sources:
        path = Path(item)
        if path.is_dir():
            candidates = sorted(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in _IMAGE_SUFFIXES
            )
        elif path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES:
            candidates = [path]
        else:
            warnings.append(f"Unsupported or missing barcode source: {path}")
            continue
        for candidate in candidates:
            key = str(candidate.resolve())
            if key in seen:
                continue
            seen.add(key)
            yield candidate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gera mappings verificados Produto↔Imagem por barcode exato quando o catálogo suporta EAN/GTIN."
    )
    parser.add_argument("sources", nargs="+", help="Imagens ou diretórios")
    parser.add_argument("--product-db", required=True, help="products.db existente, somente leitura")
    parser.add_argument("--zbarimg", default="zbarimg", help="Executável zbarimg")
    parser.add_argument("--manifest", required=True, help="Manifest JSON de mappings resolvidos")
    parser.add_argument("--report", default=None, help="Relatório JSON detalhado")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    catalog, warnings = discover_barcode_catalog(args.product_db)
    provider = ZBarImgProvider(args.zbarimg)
    result = BarcodeSeedResolver(provider, catalog).resolve(args.sources)
    result.warnings = [*warnings, *result.warnings]
    manifest_path = write_json(args.manifest, manifest_payload(result))
    payload = report_payload(result)
    payload["manifest_path"] = str(manifest_path)
    if args.report:
        payload["report_path"] = str(write_json(args.report, payload))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
