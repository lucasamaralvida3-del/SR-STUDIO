from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from srstudio.images.association import normalize_product_name, product_names_compatible


@dataclass(frozen=True, slots=True)
class EvaluationLabel:
    image_sha256: str
    product_name: str = ""
    decorative: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class DecisionView:
    image_sha256: str
    product_name: str
    status: str
    confidence: float
    consensus_ratio: float = 0.0
    distinct_source_count: int = 0
    distinct_product_count: int = 0
    alternatives: tuple[str, ...] = ()
    provenance: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class PrecisionMetrics:
    labeled_images: int
    product_labels: int
    decorative_labels: int
    product_predictions: int
    correct_product_predictions: int
    wrong_product_predictions: int
    missing_product_predictions: int
    decorative_correct: int
    decorative_wrong: int
    auto_accept_labeled: int
    auto_accept_correct: int
    auto_accept_wrong: int
    association_precision: float
    product_coverage: float
    decorative_accuracy: float
    auto_accept_precision: float


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    metrics: PrecisionMetrics
    errors: tuple[dict, ...]


def decision_view(value) -> DecisionView:
    if isinstance(value, DecisionView):
        return value
    if isinstance(value, Mapping):
        alternatives = tuple(
            str(item.get("product_name", "")) if isinstance(item, Mapping) else str(item)
            for item in value.get("alternatives", ())
            if item
        )
        provenance = []
        for evidence in value.get("evidence", ()):
            if not isinstance(evidence, Mapping):
                continue
            provenance.append(
                {
                    "source_file": str(evidence.get("source_file", "")),
                    "source_slide": int(evidence.get("source_slide", 0) or 0),
                    "source_shape": str(evidence.get("source_shape", "")),
                    "media_path": str(evidence.get("media_path", "")),
                }
            )
        return DecisionView(
            image_sha256=str(value.get("image_sha256", "")),
            product_name=str(value.get("product_name", "")),
            status=str(value.get("status", "")),
            confidence=float(value.get("confidence", 0.0) or 0.0),
            consensus_ratio=float(value.get("consensus_ratio", 0.0) or 0.0),
            distinct_source_count=int(value.get("distinct_source_count", 0) or 0),
            distinct_product_count=int(value.get("distinct_product_count", 0) or 0),
            alternatives=alternatives,
            provenance=tuple(provenance),
        )
    alternatives = tuple(
        str(getattr(item, "product_name", ""))
        for item in (getattr(value, "alternatives", ()) or ())
        if getattr(item, "product_name", "")
    )
    provenance = tuple(
        {
            "source_file": str(getattr(item, "source_file", "")),
            "source_slide": int(getattr(item, "source_slide", 0) or 0),
            "source_shape": str(getattr(item, "source_shape", "")),
            "media_path": str(getattr(item, "media_path", "")),
        }
        for item in (getattr(value, "evidence", ()) or ())
    )
    return DecisionView(
        image_sha256=str(getattr(value, "image_sha256", "")),
        product_name=str(getattr(value, "product_name", "")),
        status=str(getattr(value, "status", "")),
        confidence=float(getattr(value, "confidence", 0.0) or 0.0),
        consensus_ratio=float(getattr(value, "consensus_ratio", 0.0) or 0.0),
        distinct_source_count=int(getattr(value, "distinct_source_count", 0) or 0),
        distinct_product_count=int(getattr(value, "distinct_product_count", 0) or 0),
        alternatives=alternatives,
        provenance=provenance,
    )


def evaluate_decisions(
    decisions: Iterable,
    labels: Iterable[EvaluationLabel],
) -> EvaluationResult:
    by_sha = {
        view.image_sha256: view
        for value in decisions
        if (view := decision_view(value)).image_sha256
    }
    label_rows = [label for label in labels if label.image_sha256]
    product_labels = [label for label in label_rows if not label.decorative and label.product_name]
    decorative_labels = [label for label in label_rows if label.decorative]

    product_predictions = 0
    correct_product = 0
    wrong_product = 0
    missing_product = 0
    decorative_correct = 0
    decorative_wrong = 0
    auto_labeled = 0
    auto_correct = 0
    auto_wrong = 0
    errors: list[dict] = []

    for label in label_rows:
        decision = by_sha.get(label.image_sha256)
        if label.decorative:
            correct = decision is not None and decision.status == "decorative"
            if correct:
                decorative_correct += 1
            else:
                decorative_wrong += 1
                errors.append(_error_payload(label, decision, "decorative-misclassified"))
        else:
            if decision is None or decision.status == "decorative" or not decision.product_name:
                missing_product += 1
                correct = False
                errors.append(_error_payload(label, decision, "missing-product-prediction"))
            else:
                product_predictions += 1
                correct = _product_match(decision.product_name, label.product_name)
                if correct:
                    correct_product += 1
                else:
                    wrong_product += 1
                    errors.append(_error_payload(label, decision, "wrong-product"))

        if decision is not None and decision.status == "accepted":
            auto_labeled += 1
            if correct:
                auto_correct += 1
            else:
                auto_wrong += 1
                errors.append(_error_payload(label, decision, "wrong-auto-accept"))

    return EvaluationResult(
        metrics=PrecisionMetrics(
            labeled_images=len(label_rows),
            product_labels=len(product_labels),
            decorative_labels=len(decorative_labels),
            product_predictions=product_predictions,
            correct_product_predictions=correct_product,
            wrong_product_predictions=wrong_product,
            missing_product_predictions=missing_product,
            decorative_correct=decorative_correct,
            decorative_wrong=decorative_wrong,
            auto_accept_labeled=auto_labeled,
            auto_accept_correct=auto_correct,
            auto_accept_wrong=auto_wrong,
            association_precision=_ratio(correct_product, product_predictions),
            product_coverage=_ratio(product_predictions, len(product_labels)),
            decorative_accuracy=_ratio(decorative_correct, len(decorative_labels)),
            auto_accept_precision=_ratio(auto_correct, auto_labeled),
        ),
        errors=tuple(errors),
    )


def sample_for_manual_review(
    decisions: Iterable,
    *,
    random_count: int = 20,
    hard_count: int = 20,
    seed: int = 20260818,
) -> list[DecisionView]:
    rows = [decision_view(value) for value in decisions]
    rows = [row for row in rows if row.image_sha256]
    hard = sorted(
        rows,
        key=lambda row: (
            _hardness(row),
            row.confidence,
            row.image_sha256,
        ),
        reverse=True,
    )[: max(0, int(hard_count))]
    hard_ids = {row.image_sha256 for row in hard}
    remaining = [row for row in rows if row.image_sha256 not in hard_ids]
    rng = random.Random(seed)
    random_rows = rng.sample(remaining, min(max(0, int(random_count)), len(remaining)))
    return [*hard, *random_rows]


def load_labels(path: str | Path) -> list[EvaluationLabel]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("labels", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Evaluation labels must be a list or {'labels': [...]} object")
    result: list[EvaluationLabel] = []
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("image_sha256"):
            continue
        result.append(
            EvaluationLabel(
                image_sha256=str(row["image_sha256"]),
                product_name=str(row.get("product_name", "")),
                decorative=bool(row.get("decorative", False)),
                note=str(row.get("note", "")),
            )
        )
    return result


def load_batch_decisions(path: str | Path) -> list[DecisionView]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("decisions", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        raise ValueError("Batch report decisions must be a list")
    return [decision_view(row) for row in rows]


def result_payload(result: EvaluationResult) -> dict:
    return {
        "metrics": asdict(result.metrics),
        "errors": list(result.errors),
    }


def sample_payload(rows: Iterable[DecisionView]) -> dict:
    return {"sample": [asdict(row) for row in rows]}


def write_json(path: str | Path, payload: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(target)
    return target


def _product_match(predicted: str, expected: str) -> bool:
    left = normalize_product_name(predicted)
    right = normalize_product_name(expected)
    return bool(left and right and (left == right or product_names_compatible(left, right)))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _hardness(row: DecisionView) -> float:
    score = 0.0
    if row.status == "review":
        score += 3.0
    elif row.status == "probable":
        score += 2.2
    elif row.status == "accepted":
        score += 1.0
    if row.distinct_product_count > 1:
        score += min(2.0, 0.5 * (row.distinct_product_count - 1))
    if row.alternatives:
        score += min(1.5, 0.5 * len(row.alternatives))
    score += max(0.0, 1.0 - row.consensus_ratio)
    if 0.78 <= row.confidence <= 0.93:
        score += 0.8
    return score


def _error_payload(label: EvaluationLabel, decision: DecisionView | None, reason: str) -> dict:
    return {
        "reason": reason,
        "image_sha256": label.image_sha256,
        "expected_product": label.product_name,
        "expected_decorative": label.decorative,
        "predicted_product": decision.product_name if decision else "",
        "predicted_status": decision.status if decision else "missing",
        "predicted_confidence": decision.confidence if decision else 0.0,
        "note": label.note,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Avalia precisão Produto↔Imagem e gera amostra manual determinística.")
    parser.add_argument("--batch-report", required=True, help="JSON produzido por image batch training")
    parser.add_argument("--labels", default=None, help="Ground truth JSON opcional")
    parser.add_argument("--evaluation-report", default=None, help="Saída da avaliação")
    parser.add_argument("--sample-report", default=None, help="Saída da amostra para revisão manual")
    parser.add_argument("--random-count", type=int, default=20)
    parser.add_argument("--hard-count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260818)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    decisions = load_batch_decisions(args.batch_report)
    payload: dict = {}
    if args.labels:
        result = evaluate_decisions(decisions, load_labels(args.labels))
        payload["evaluation"] = result_payload(result)
        if args.evaluation_report:
            write_json(args.evaluation_report, payload["evaluation"])
    sample = sample_for_manual_review(
        decisions,
        random_count=args.random_count,
        hard_count=args.hard_count,
        seed=args.seed,
    )
    payload["sample"] = sample_payload(sample)
    if args.sample_report:
        write_json(args.sample_report, payload["sample"])
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
