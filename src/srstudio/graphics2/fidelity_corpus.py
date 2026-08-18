from __future__ import annotations

"""Agregação transversal dos relatórios ``*-impact.json`` de Golden Masters.

O Reference Suite mede cada página isoladamente. Este módulo responde à pergunta
mais útil para priorização sistêmica: quais categorias aparecem em vários casos
e quanto do gap total estimado elas concentram, sem alterar o Fidelity Gate.
"""

from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Iterable
import json

from .fidelity_impact import FIDELITY_CATEGORIES

_PRIORITY_RANK = {"P1": 3, "P2": 2, "P3": 1}


def aggregate_fidelity_corpus(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(item or {}) for item in cases]
    by_category: dict[str, dict[str, Any]] = {
        category: {
            "category": category,
            "cases_affected": 0,
            "regions": 0,
            "importance": 0.0,
            "estimated_score_loss": 0.0,
            "estimated_percentage_points": 0.0,
            "priority": "P3",
            "case_names": [],
        }
        for category in FIDELITY_CATEGORIES
    }
    total_gap = 0.0
    valid_cases = 0

    for index, case in enumerate(rows):
        impact = dict(case.get("impact") or case)
        categories = list(impact.get("categories") or [])
        if not categories and "score_gap" not in impact:
            continue
        valid_cases += 1
        total_gap += max(0.0, float(impact.get("score_gap") or 0.0))
        name = str(case.get("name") or impact.get("name") or f"case-{index + 1}")
        seen: set[str] = set()
        for raw in categories:
            if not isinstance(raw, dict):
                continue
            category = str(raw.get("category") or "RENDER").upper()
            if category not in by_category:
                category = "RENDER"
            target = by_category[category]
            if category not in seen:
                target["cases_affected"] += 1
                target["case_names"].append(name)
                seen.add(category)
            target["regions"] += max(0, int(raw.get("regions") or 0))
            target["importance"] += max(0.0, float(raw.get("importance") or 0.0))
            loss = max(0.0, float(raw.get("estimated_score_loss") or 0.0))
            target["estimated_score_loss"] += loss
            target["estimated_percentage_points"] += loss * 100.0
            priority = str(raw.get("priority") or "P3").upper()
            if _PRIORITY_RANK.get(priority, 0) > _PRIORITY_RANK[target["priority"]]:
                target["priority"] = priority

    categories_out: list[dict[str, Any]] = []
    for category in FIDELITY_CATEGORIES:
        item = by_category[category]
        if item["cases_affected"] <= 0:
            continue
        item["corpus_case_ratio"] = item["cases_affected"] / valid_cases if valid_cases else 0.0
        item["corpus_gap_share"] = (
            item["estimated_score_loss"] / total_gap if total_gap > 0.0 else 0.0
        )
        categories_out.append(item)

    categories_out.sort(
        key=lambda item: (
            item["estimated_score_loss"],
            item["cases_affected"],
            item["importance"],
        ),
        reverse=True,
    )
    systemic = [
        item["category"]
        for item in categories_out
        if item["cases_affected"] >= 2 and item["corpus_gap_share"] >= 0.08
    ]
    return {
        "cases": valid_cases,
        "total_score_gap": total_gap,
        "total_percentage_points": total_gap * 100.0,
        "systemic_categories": systemic,
        "categories": categories_out,
        "estimation": "sum-of-case-score-gap-proportional-to-triage-importance",
    }


def load_impact_reports(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for source in paths:
        path = Path(source)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
            for case in payload["cases"]:
                if isinstance(case, dict) and isinstance(case.get("impact"), dict):
                    loaded.append({"name": case.get("name", path.stem), "impact": case["impact"]})
            continue
        if isinstance(payload, dict):
            loaded.append({"name": path.stem, "impact": payload})
    return loaded


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-fidelity-corpus",
        description="Agrega causas de fidelidade de vários relatórios impact.json.",
    )
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("build/fidelity/corpus-impact.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = aggregate_fidelity_corpus(load_impact_reports(args.reports))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"SR Fidelity Corpus: {payload['cases']} caso(s) · "
        f"gap acumulado {payload['total_percentage_points']:.2f} pp · "
        f"sistêmicas {', '.join(payload['systemic_categories']) or 'nenhuma'} · {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
