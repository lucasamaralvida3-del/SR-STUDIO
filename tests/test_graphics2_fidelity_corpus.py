from __future__ import annotations

import pytest

from srstudio.graphics2.fidelity_corpus import aggregate_fidelity_corpus


def test_corpus_aggregation_ranks_shared_categories_by_estimated_gap() -> None:
    cases = [
        {
            "name": "A",
            "impact": {
                "score_gap": 0.10,
                "categories": [
                    {
                        "category": "TEXT",
                        "priority": "P1",
                        "regions": 3,
                        "importance": 80.0,
                        "estimated_score_loss": 0.08,
                    },
                    {
                        "category": "IMAGE",
                        "priority": "P2",
                        "regions": 1,
                        "importance": 20.0,
                        "estimated_score_loss": 0.02,
                    },
                ],
            },
        },
        {
            "name": "B",
            "impact": {
                "score_gap": 0.20,
                "categories": [
                    {
                        "category": "TEXT",
                        "priority": "P1",
                        "regions": 4,
                        "importance": 70.0,
                        "estimated_score_loss": 0.14,
                    },
                    {
                        "category": "CROP",
                        "priority": "P1",
                        "regions": 2,
                        "importance": 30.0,
                        "estimated_score_loss": 0.06,
                    },
                ],
            },
        },
    ]

    result = aggregate_fidelity_corpus(cases)

    assert result["cases"] == 2
    assert result["total_score_gap"] == pytest.approx(0.30)
    assert result["categories"][0]["category"] == "TEXT"
    assert result["categories"][0]["cases_affected"] == 2
    assert result["categories"][0]["estimated_percentage_points"] == pytest.approx(22.0)
    assert result["categories"][0]["corpus_gap_share"] == pytest.approx(0.22 / 0.30)
    assert result["systemic_categories"] == ["TEXT"]


def test_corpus_aggregation_accepts_raw_impact_payloads_and_unknown_category() -> None:
    result = aggregate_fidelity_corpus(
        [
            {
                "score_gap": 0.05,
                "categories": [
                    {
                        "category": "OTHER",
                        "priority": "P3",
                        "regions": 1,
                        "importance": 10.0,
                        "estimated_score_loss": 0.05,
                    }
                ],
            }
        ]
    )

    assert result["cases"] == 1
    assert result["categories"][0]["category"] == "RENDER"
    assert result["categories"][0]["case_names"] == ["case-1"]
    assert result["systemic_categories"] == []
