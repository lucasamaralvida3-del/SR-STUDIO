from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from srstudio.images.corpus_training import ProductImageCorpusTrainer
from srstudio.images.library import ImageLibrary
from srstudio.images.lookup import ProductImageLookupService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build/update the SR Studio product-image bank from Canva/PPTX corpus files."
    )
    parser.add_argument("sources", nargs="+", help="PPTX, ZIP or directories containing PPTX files")
    parser.add_argument("--bank-root", required=True, help="Persistent ImageLibrary directory")
    parser.add_argument(
        "--imports-root",
        default="",
        help="Persistent extraction/state directory; defaults to <bank-root>/training",
    )
    parser.add_argument("--report", default="", help="Optional JSON report path")
    parser.add_argument("--force", action="store_true", help="Reprocess sources even when their SHA-256 is unchanged")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Validate a product lookup after training; may be repeated",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bank_root = Path(args.bank_root).expanduser().resolve()
    imports_root = (
        Path(args.imports_root).expanduser().resolve()
        if args.imports_root
        else bank_root / "training"
    )
    library = ImageLibrary(bank_root)
    trainer = ProductImageCorpusTrainer(library, imports_root=imports_root)
    report = trainer.train([Path(value).expanduser() for value in args.sources], force=args.force)

    lookups: list[dict] = []
    if args.query:
        lookup = ProductImageLookupService(library)
        for query in args.query:
            result = lookup.find_image(query)
            best = result.best_match
            lookups.append(
                {
                    "query": query,
                    "confidence": result.confidence,
                    "best_match": _candidate_json(best) if best else None,
                    "alternatives": [_candidate_json(item) for item in result.alternatives],
                }
            )

    payload = {
        "metrics": asdict(report.metrics),
        "warnings": report.warnings,
        "processed_files": report.processed_files,
        "skipped_files": report.skipped_files,
        "decisions": [
            {
                "image_sha256": item.image_sha256,
                "product_name": item.product_name,
                "normalized_name": item.normalized_name,
                "confidence": item.confidence,
                "status": item.status,
                "consensus_ratio": item.consensus_ratio,
                "source_count": item.source_count,
                "distinct_source_count": item.distinct_source_count,
                "observation_count": item.observation_count,
                "distinct_product_count": item.distinct_product_count,
                "alternatives": [asdict(alt) for alt in item.alternatives],
            }
            for item in report.decisions
        ],
        "lookups": lookups,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if not report.warnings else 2


def _candidate_json(candidate) -> dict:
    asset = candidate.asset
    return {
        "asset_id": getattr(asset, "id", ""),
        "product_name": getattr(asset, "product_name", ""),
        "path": getattr(asset, "path", ""),
        "score": candidate.score,
        "reason": candidate.reason,
        "confidence": getattr(asset, "confidence", 0.0),
        "source_file": getattr(asset, "source_file", ""),
        "slide_index": getattr(asset, "slide_index", 0),
    }


if __name__ == "__main__":
    raise SystemExit(main())
