from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "visual-fidelity" / "g2-official-corpus-v1.json"


def test_official_visual_corpus_v1_keeps_png_approval_gate_separate_from_provisional_baseline() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert payload["status"] == "baseline_established_pending_png_reference"
    assert payload["approved_cases"] == []
    assert payload["provisional_cases"] == 11
    assert len(payload["candidates"]) == 3
    assert all(
        candidate["reference_status"] == "provisional-jpeg-only"
        for candidate in payload["candidates"]
    )
    assert payload["baseline_policy"]["thresholds"] is None
