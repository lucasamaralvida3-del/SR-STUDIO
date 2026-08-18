from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from srstudio.images.corpus_inventory import PptxCorpusInventory
from srstudio.images.lookup import ProductImageLookupService
from srstudio.images.safe_library import SafeImageLibrary


@dataclass(frozen=True, slots=True)
class LookupBenchmark:
    assets: int
    refresh_ms: float
    queries: int
    median_ms: float
    p95_ms: float
    max_ms: float
    matches: int


@dataclass(frozen=True, slots=True)
class InventoryBenchmark:
    files: int
    slides: int
    unique_media: int
    elapsed_ms: float


def benchmark_lookup(
    library,
    queries: list[str],
    *,
    repeats: int = 100,
) -> LookupBenchmark:
    service = ProductImageLookupService(library)
    started = time.perf_counter()
    service.refresh()
    refresh_ms = (time.perf_counter() - started) * 1000.0

    samples: list[float] = []
    matches = 0
    query_values = [value for value in queries if str(value).strip()]
    for _ in range(max(1, int(repeats))):
        for query in query_values:
            started = time.perf_counter()
            result = service.find_image(query)
            samples.append((time.perf_counter() - started) * 1000.0)
            if result.best_match is not None:
                matches += 1

    samples.sort()
    p95_index = max(0, min(len(samples) - 1, int(len(samples) * 0.95) - 1)) if samples else 0
    return LookupBenchmark(
        assets=len(service._assets),
        refresh_ms=round(refresh_ms, 6),
        queries=len(samples),
        median_ms=round(statistics.median(samples), 6) if samples else 0.0,
        p95_ms=round(samples[p95_index], 6) if samples else 0.0,
        max_ms=round(max(samples), 6) if samples else 0.0,
        matches=matches,
    )


def benchmark_inventory(sources: list[str]) -> InventoryBenchmark:
    started = time.perf_counter()
    report = PptxCorpusInventory().scan(sources)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return InventoryBenchmark(
        files=report.metrics.files_found,
        slides=report.metrics.slides,
        unique_media=report.metrics.unique_media_exact,
        elapsed_ms=round(elapsed_ms, 6),
    )


def write_report(path: str | Path, payload: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(target)
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark do banco Produto↔Imagem sem carregar imagens na busca.")
    parser.add_argument("--library", required=True, help="Diretório do banco de imagens")
    parser.add_argument("--query", action="append", default=[], help="Consulta real; pode repetir")
    parser.add_argument("--repeats", type=int, default=100, help="Repetições por consulta")
    parser.add_argument("--corpus", action="append", default=[], help="PPTX/diretório para medir inventário")
    parser.add_argument("--report", default=None, help="Grava JSON com as medições")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    library = SafeImageLibrary(args.library)
    lookup = benchmark_lookup(library, args.query, repeats=args.repeats)
    payload = {"lookup": asdict(lookup)}
    if args.corpus:
        payload["inventory"] = asdict(benchmark_inventory(args.corpus))
    if args.report:
        payload["report_path"] = str(write_report(args.report, payload))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
