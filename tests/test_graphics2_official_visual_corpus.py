from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "visual-fidelity" / "g2-official-corpus-v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_CASE_FIELDS = {
    "case_id",
    "source_pptx",
    "source_pptx_sha256",
    "slide_number",
    "reference_png",
    "reference_png_sha256",
    "width",
    "height",
    "source_type",
    "notes",
}
LEGACY_CASE_TOKENS = {
    "CARTAZ_VENDA",
    "SEGUNDA_DA_LIMPEZA",
    "CLUBE_EXCLUSIVO",
    "ATACADO_LEGACY",
}


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_g2_official_corpus_is_explicitly_graphics2_only_and_measure_first() -> None:
    payload = _registry()
    assert payload["schema"] == "srstudio/g2-official-visual-corpus-1"
    assert payload["product"] == "SR Studio de Encartes G2"
    assert payload["scope"] == "graphics2-only"
    assert payload["baseline_policy"]["thresholds"] is None
    assert payload["baseline_policy"]["rule"] == "measure-first"
    assert set(payload["forbidden_legacy_gates"]) == LEGACY_CASE_TOKENS


def test_approved_g2_cases_require_complete_hash_pinned_provenance() -> None:
    payload = _registry()
    seen: set[str] = set()
    for case in payload["approved_cases"]:
        assert REQUIRED_CASE_FIELDS <= case.keys()
        assert case["case_id"] not in seen
        seen.add(case["case_id"])
        assert SHA256_RE.fullmatch(case["source_pptx_sha256"])
        assert SHA256_RE.fullmatch(case["reference_png_sha256"])
        assert case["reference_png"].lower().endswith(".png")
        assert int(case["slide_number"]) >= 1
        assert int(case["width"]) > 0
        assert int(case["height"]) > 0
        assert case["source_type"] in {"canva", "powerpoint"}
        haystack = " ".join(str(value) for value in case.values()).upper()
        for token in LEGACY_CASE_TOKENS:
            assert token not in haystack


def test_candidates_cannot_be_silently_promoted_without_official_reference() -> None:
    payload = _registry()
    assert payload["candidates"], "At least one real G2 source candidate should be tracked"
    for candidate in payload["candidates"]:
        assert SHA256_RE.fullmatch(candidate["source_pptx_sha256"])
        if candidate["reference_status"] != "verified":
            assert candidate["candidate_id"] not in {
                case["case_id"] for case in payload["approved_cases"]
            }


def test_registry_records_immutable_baseline_contract() -> None:
    policy = _registry()["immutability"]
    assert policy["approved_cases_are_append_only"] is True
    assert policy["reference_replacement_requires_new_case_version"] is True
    assert policy["source_or_reference_hash_mismatch_is_fatal"] is True


def test_private_corpus_hash_guard_rejects_wrong_source(tmp_path: Path) -> None:
    candidate = _registry()["candidates"][0]
    source = tmp_path / candidate["source_pptx"]
    source.write_bytes(b"wrong source")
    digest = sha256(source.read_bytes()).hexdigest()
    assert digest != candidate["source_pptx_sha256"]
    with pytest.raises(ValueError, match="SHA-256"):
        if digest != candidate["source_pptx_sha256"]:
            raise ValueError(
                f"SHA-256 do PPTX divergente: esperado {candidate['source_pptx_sha256']}, atual {digest}"
            )


def test_rejected_reference_candidates_are_not_approved_cases() -> None:
    payload = _registry()
    approved_refs = {case["reference_png"] for case in payload["approved_cases"]}
    for rejected in payload["rejected_reference_candidates"]:
        assert rejected["file"] not in approved_refs
        assert rejected["reason"].strip()
