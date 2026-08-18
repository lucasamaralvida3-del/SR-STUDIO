from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "visual-fidelity" / "g2-official-corpus-v1.json"


def test_official_visual_corpus_v1_has_no_unverified_approved_case() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert payload["status"] == "awaiting-official-references"
    assert payload["approved_cases"] == []
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["reference_status"] == "missing-direct-export"
