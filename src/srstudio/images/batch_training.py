from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from srstudio.images.corpus_inventory import CorpusInventoryReport, PptxCorpusInventory, report_payload as inventory_payload
from srstudio.images.corpus_training import CorpusTrainingReport
from srstudio.images.evidence_aliases import AliasLearningStats, apply_evidence_aliases
from srstudio.images.lookup import ProductImageLookupService
from srstudio.images.precision_training import PrecisionProductImageCorpusTrainer
from srstudio.images.safe_library import SafeImageLibrary


@dataclass(slots=True)
class BatchTrainingResult:
    inventory: CorpusInventoryReport
    report: CorpusTrainingReport
    aliases: AliasLearningStats
    lookups: dict[str, dict]


def run_batch_training(
    sources: Iterable[str | Path],
    *,
    library_root: str | Path,
    imports_root: str | Path,
    state_path: str | Path | None = None,
    force: bool = False,
    queries: Iterable[str] = (),
) -> BatchTrainingResult:
    """Run INVENTORY→TRAIN→ALIASES→LOOKUP as one precision-first pipeline."""
    source_items = list(sources)
    inventory = PptxCorpusInventory().scan(source_items)
    library = SafeImageLibrary(library_root)
    trainer = PrecisionProductImageCorpusTrainer(
        library,
        imports_root=imports_root,
        state_path=state_path,
    )
    report = trainer.train(source_items, force=force)
    alias_stats = apply_evidence_aliases(library, report.decisions)

    lookup_service = ProductImageLookupService(library)
    lookup_payload = {
        query: _lookup_payload(lookup_service.find_image(query))
        for query in queries
        if str(query).strip()
    }
    return BatchTrainingResult(inventory, report, alias_stats, lookup_payload)


def result_payload(result: BatchTrainingResult) -> dict:
    return {
        "inventory": inventory_payload(result.inventory),
        "metrics": asdict(result.report.metrics),
        "warnings": list(result.report.warnings),
        "processed_files": list(result.report.processed_files),
        "skipped_files": list(result.report.skipped_files),
        "aliases": asdict(result.aliases),
        "decisions": [_decision_payload(decision) for decision in result.report.decisions],
        "lookups": result.lookups,
    }


def write_report(path: str | Path, result: BatchTrainingResult) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(result_payload(result), ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(target)
    return target


def _decision_payload(decision) -> dict:
    return {
        "image_sha256": decision.image_sha256,
        "product_name": decision.product_name,
        "normalized_name": decision.normalized_name,
        "confidence": decision.confidence,
        "status": decision.status,
        "consensus_ratio": decision.consensus_ratio,
        "source_count": decision.source_count,
        "distinct_source_count": decision.distinct_source_count,
        "observation_count": decision.observation_count,
        "distinct_product_count": decision.distinct_product_count,
        "alternatives": [asdict(item) for item in decision.alternatives],
        "evidence": [asdict(item) for item in decision.evidence],
    }


def _lookup_payload(result) -> dict:
    return {
        "confidence": result.confidence,
        "best_match": _candidate_payload(result.best_match),
        "alternatives": [_candidate_payload(item) for item in result.alternatives],
    }


def _candidate_payload(candidate) -> dict | None:
    if candidate is None:
        return None
    asset = candidate.asset
    return {
        "image_id": getattr(asset, "id", ""),
        "path": getattr(asset, "path", ""),
        "product_name": getattr(asset, "product_name", ""),
        "product_key": getattr(asset, "product_key", ""),
        "confidence": getattr(asset, "confidence", 0.0),
        "review_status": getattr(asset, "review_status", ""),
        "source": getattr(asset, "source", ""),
        "source_file": getattr(asset, "source_file", ""),
        "slide_index": getattr(asset, "slide_index", 0),
        "score": candidate.score,
        "reason": candidate.reason,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventaria e treina incrementalmente o banco Produto↔Imagem usando Canva/PPTX estruturado."
    )
    parser.add_argument("sources", nargs="+", help="PPTX, ZIP ou diretórios contendo PPTX")
    parser.add_argument("--library", required=True, help="Diretório persistente do banco de imagens")
    parser.add_argument("--imports-root", required=True, help="Diretório de assets/estado extraídos do corpus")
    parser.add_argument("--state", default=None, help="Caminho opcional do estado incremental JSON")
    parser.add_argument("--report", default=None, help="Grava relatório JSON detalhado")
    parser.add_argument("--force", action="store_true", help="Reprocessa fontes já conhecidas")
    parser.add_argument("--query", action="append", default=[], help="Valida uma busca de produto após o treino")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_batch_training(
        args.sources,
        library_root=args.library,
        imports_root=args.imports_root,
        state_path=args.state,
        force=args.force,
        queries=args.query,
    )
    payload = result_payload(result)
    if args.report:
        payload["report_path"] = str(write_report(args.report, result))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
