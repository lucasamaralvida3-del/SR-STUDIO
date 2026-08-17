from __future__ import annotations

from srstudio.graphics2.fidelity_diagnostics import compact_fidelity_triage, store_fidelity_triage
from srstudio.graphics2.model import GraphicsDocument


def test_compact_triage_strips_local_artifact_paths_and_copies_payload() -> None:
    source = {
        "available": True,
        "triage_report": "build/fidelity/quinta-triage.json",
        "heatmap": "build/fidelity/quinta-heatmap.png",
        "attribution_report": "build/fidelity/quinta-attribution.json",
        "spatial": {"changed_ratio": 0.12, "regions": [{"x": 10}]},
        "attribution": {
            "regions": [
                {
                    "region_index": 1,
                    "suspects": [
                        {
                            "node_id": "price_reais",
                            "binding_role": "price_reais",
                            "diagnostic_hint": "preço: revisar baseline",
                        }
                    ],
                }
            ]
        },
    }

    compact = compact_fidelity_triage(source)

    assert compact["available"] is True
    assert "triage_report" not in compact
    assert "heatmap" not in compact
    assert "attribution_report" not in compact
    assert compact["attribution"]["regions"][0]["suspects"][0]["node_id"] == "price_reais"

    source["attribution"]["regions"][0]["suspects"][0]["node_id"] = "mutated"
    assert compact["attribution"]["regions"][0]["suspects"][0]["node_id"] == "price_reais"


def test_store_triage_keeps_diagnostic_outside_production_gate_contract() -> None:
    document = GraphicsDocument(name="Quinta Filé")
    store_fidelity_triage(
        document,
        {
            "available": False,
            "reason": "Triagem visual exige imagens com o mesmo tamanho.",
            "triage_report": "local.json",
        },
    )

    stored = document.metadata["visual_fidelity_triage_last"]
    assert stored == {
        "available": False,
        "reason": "Triagem visual exige imagens com o mesmo tamanho.",
    }
