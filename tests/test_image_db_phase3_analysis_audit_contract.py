from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.ci import image_db_phase3_analysis as analysis
from srstudio.images.association import normalize_product_name


def _asset(*, product_name: str = "", product_key: str = "", canonical_sha256: str = "", sha256: str = ""):
    metadata = {}
    if canonical_sha256:
        metadata["canonical_sha256"] = canonical_sha256
    if sha256:
        metadata["sha256"] = sha256
    return SimpleNamespace(product_name=product_name, product_key=product_key, metadata=metadata)


def _not_found_row(query: str) -> dict:
    return {
        "query": query,
        "found": False,
        "best_product_name": "",
        "best_product_key": "",
        "image_id": "",
        "asset_review_status": "",
        "asset_confidence": 0.0,
        "confidence": 0.0,
        "match_type": "none",
        "quality_score": 0.0,
        "provenance": [],
    }


def test_negative_invariant_clean_fixture_is_calculated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis, "_lookup_row", lambda _service, query: _not_found_row(query))
    rows = analysis._run_negative_invariants(object())
    assert len(rows) == len(analysis.NEGATIVE_CASES)
    assert all(row["violated"] is False for row in rows)
    assert sum(1 for row in rows if row["violated"]) == 0


def test_negative_invariant_positive_fixture_is_not_hardcoded(monkeypatch: pytest.MonkeyPatch) -> None:
    forbidden_by_query = dict(analysis.NEGATIVE_CASES)
    first_query = analysis.NEGATIVE_CASES[0][0]

    def lookup(_service, query: str) -> dict:
        if query != first_query:
            return _not_found_row(query)
        row = _not_found_row(query)
        row.update(
            found=True,
            best_product_name=forbidden_by_query[query],
            asset_review_status="pending",
            match_type="exact",
        )
        return row

    monkeypatch.setattr(analysis, "_lookup_row", lookup)
    rows = analysis._run_negative_invariants(object())
    assert sum(1 for row in rows if row["violated"]) == 1
    assert next(row for row in rows if row["query"] == first_query)["violated"] is True


def test_duplicate_logical_clean_fixture() -> None:
    summary = analysis._logical_association_summary(
        [
            _asset(product_name="PRODUTO A", canonical_sha256="sha-a"),
            _asset(product_name="PRODUTO B", canonical_sha256="sha-b"),
        ]
    )
    assert summary["logical_associations_total"] == 2
    assert summary["unique_logical_associations"] == 2
    assert summary["duplicate_logical_associations"] == 0
    assert summary["duplicate_logical_examples"] == []


def test_duplicate_logical_pair_counts_one_extra_observation() -> None:
    summary = analysis._logical_association_summary(
        [
            _asset(product_name="PRODUTO A", canonical_sha256="same-sha"),
            _asset(product_name="PRODUTO A", canonical_sha256="same-sha"),
        ]
    )
    assert summary["logical_associations_total"] == 2
    assert summary["unique_logical_associations"] == 1
    assert summary["duplicate_logical_associations"] == 1
    assert summary["duplicate_logical_examples"][0]["count"] == 2


def test_duplicate_logical_triple_counts_two_extra_observations() -> None:
    summary = analysis._logical_association_summary(
        [
            _asset(product_name="PRODUTO A", canonical_sha256="same-sha"),
            _asset(product_name="PRODUTO A", canonical_sha256="same-sha"),
            _asset(product_name="PRODUTO A", canonical_sha256="same-sha"),
        ]
    )
    assert summary["logical_associations_total"] == 3
    assert summary["unique_logical_associations"] == 1
    assert summary["duplicate_logical_associations"] == 2


def test_duplicate_logical_sha_fallback_uses_sha256() -> None:
    summary = analysis._logical_association_summary(
        [
            _asset(product_name="PRODUTO A", sha256="fallback-sha"),
            _asset(product_name="PRODUTO A", sha256="fallback-sha"),
        ]
    )
    assert summary["duplicate_logical_associations"] == 1
    assert summary["duplicate_logical_examples"][0]["canonical_sha"] == "fallback-sha"


def test_duplicate_logical_uses_real_product_normalization() -> None:
    first = "CAFÉ VASCONCELOS 500G"
    second = "cafe vasconcelos 500g"
    assert first != second
    assert normalize_product_name(first) == normalize_product_name(second)
    summary = analysis._logical_association_summary(
        [
            _asset(product_name=first, canonical_sha256="same-sha"),
            _asset(product_name=second, canonical_sha256="same-sha"),
        ]
    )
    assert summary["duplicate_logical_associations"] == 1


def test_product_name_precedes_product_key_in_logical_identity() -> None:
    summary = analysis._logical_association_summary(
        [
            _asset(product_name="PRODUTO A", product_key="IGNORADO", canonical_sha256="same-sha"),
            _asset(product_name="produto a", product_key="OUTRO", canonical_sha256="same-sha"),
        ]
    )
    assert summary["duplicate_logical_associations"] == 1


def test_audit_schema_contract_requires_all_nonnegative_integer_fields() -> None:
    metrics = {
        "associations_without_provenance": 0,
        "negative_invariant_violations": 0,
        "duplicate_logical_associations": 0,
        "logical_associations_total": 4,
        "unique_logical_associations": 4,
    }
    analysis._validate_audit_schema({"metrics": metrics})

    for field in tuple(metrics):
        missing = dict(metrics)
        missing.pop(field)
        with pytest.raises(AssertionError, match="missing"):
            analysis._validate_audit_schema({"metrics": missing})

    invalid = dict(metrics)
    invalid["negative_invariant_violations"] = -1
    with pytest.raises(AssertionError, match="non-negative integer"):
        analysis._validate_audit_schema({"metrics": invalid})


def test_duplicate_accounting_identity_is_total_minus_unique() -> None:
    summary = analysis._logical_association_summary(
        [
            _asset(product_name="A", canonical_sha256="1"),
            _asset(product_name="A", canonical_sha256="1"),
            _asset(product_name="B", canonical_sha256="2"),
        ]
    )
    assert summary["logical_associations_total"] >= summary["unique_logical_associations"]
    assert summary["duplicate_logical_associations"] == (
        summary["logical_associations_total"] - summary["unique_logical_associations"]
    )
