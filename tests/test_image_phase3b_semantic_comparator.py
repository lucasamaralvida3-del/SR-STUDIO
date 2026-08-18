from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ci import image_db_phase3b as phase3b


BASE_COVERAGE = {
    "total": 520,
    "auto_approved": 2,
    "likely": 42,
    "review_required": 7,
    "missing": 469,
    "any_candidate": 51,
    "any_candidate_coverage_percent": 9.8077,
    "auto_approved_coverage_percent": 0.3846,
}
BASE_DEPARTMENTS = {"catalog_products": 520, "departments": [{"department": "mercearia", "total": 75}]}


class _FakeLibrary:
    def __init__(self, assets):
        self._assets = list(assets)

    def all(self):
        return list(self._assets)


def _asset(path: Path, *, product: str = "TODDY 370G", aliases=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"semantic-comparator-fixture")
    return SimpleNamespace(
        path=str(path),
        product_name=product,
        product_key=product.lower().replace(" ", "-"),
        review_status="pending",
        confidence=0.87,
        perceptual_hash="0123456789abcdef",
        aliases=tuple(aliases if aliases is not None else (product,)),
        source_file="source.pptx",
        source="phase3-test",
        metadata={
            "sha256_full": "a" * 64,
            "sha256": "a" * 64,
            "variant_sha256": ["b" * 64],
            "association_status": "probable",
            "standalone": True,
            "provenance": [
                {
                    "source_kind": "github-release-standalone",
                    "source_file": "standalone/product.png",
                    "asset_id": 519806747,
                    "release_tag": "image-db-corpus-v1",
                }
            ],
        },
    )


def _install_compare_fakes(monkeypatch, libraries, coverage=None, departments=None):
    coverage = coverage or {}
    departments = departments or {}

    def fake_library(root):
        return _FakeLibrary(libraries[str(Path(root))])

    def fake_coverage(root, _product_db):
        key = str(Path(root))
        return (
            deepcopy(coverage.get(key, BASE_COVERAGE)),
            deepcopy(departments.get(key, BASE_DEPARTMENTS)),
        )

    monkeypatch.setattr(phase3b, "SafeImageLibrary", fake_library)
    monkeypatch.setattr(phase3b, "_coverage_for_library", fake_coverage)


def _compare(monkeypatch, tmp_path, left_assets, right_assets, *, coverage=None, departments=None):
    left_root = tmp_path / "left-library"
    right_root = tmp_path / "right-library"
    output = tmp_path / "comparison.json"
    libraries = {str(left_root): left_assets, str(right_root): right_assets}
    _install_compare_fakes(monkeypatch, libraries, coverage=coverage, departments=departments)
    rc = phase3b.compare_libraries(
        Namespace(
            left_library=str(left_root),
            right_library=str(right_root),
            product_db=str(tmp_path / "catalog.db"),
            output=str(output),
        )
    )
    import json

    return rc, json.loads(output.read_text(encoding="utf-8")), left_root, right_root


def test_semantic_comparator_normalizes_aliases_as_unique_set(monkeypatch, tmp_path):
    left = _asset(
        tmp_path / "same.png",
        product="FLOCAO SINHA 400G",
        aliases=("FLOCÃO SINHÁ 400 g", "FLOCAO SINHA 400G", "  FLOCAO\nSINHA 400 G  "),
    )
    right = deepcopy(left)
    right.aliases = ("FLOCAO SINHA 400G",)

    rc, result, _, _ = _compare(monkeypatch, tmp_path, [left], [right])

    assert rc == 0
    assert result["pass"] is True
    assert result["semantic_signature_equal"] is True
    assert result["logical_signature_equal"] is True
    assert result["left"]["semantic_signature_sha256"] == result["right"]["semantic_signature_sha256"]
    assert result["comparator_contract"]["aliases"] == "normalize_product_name + unique set"


@pytest.mark.parametrize(
    ("left_product", "right_product"),
    [
        ("ARROZ PATOSUL 5KG", "ARROZ VASCONCELOS 5KG"),
        ("TODDY 370G", "TODDY 750G"),
        ("LEITE TRIANGULO 1L", "LEITE TRIANGULO 500ML"),
        ("REFRIGERANTE COLA ZERO 2L", "REFRIGERANTE COLA TRADICIONAL 2L"),
        ("MONSTER ZERO 473ML", "MONSTER ORIGINAL 473ML"),
    ],
    ids=["brand", "grammage", "volume", "flavor-variant", "sku-variant"],
)
def test_semantic_comparator_rejects_product_identity_differences(
    monkeypatch, tmp_path, left_product, right_product
):
    left = _asset(tmp_path / "identity.png", product=left_product, aliases=("CATALOG ALIAS",))
    right = deepcopy(left)
    right.product_name = right_product
    right.product_key = right_product.lower().replace(" ", "-")

    rc, result, _, _ = _compare(monkeypatch, tmp_path, [left], [right])

    assert rc == 31
    assert result["pass"] is False
    assert result["semantic_signature_equal"] is False


@pytest.mark.parametrize(
    "difference",
    [
        "image_sha",
        "review_status",
        "confidence",
        "perceptual_hash",
        "alias_identity",
        "variant_sha",
        "association_status",
        "provenance",
        "standalone_flag",
    ],
)
def test_semantic_comparator_rejects_real_asset_state_differences(monkeypatch, tmp_path, difference):
    left = _asset(tmp_path / "asset-state.png")
    right = deepcopy(left)

    if difference == "image_sha":
        right.metadata["sha256_full"] = "c" * 64
        right.metadata["sha256"] = "c" * 64
    elif difference == "review_status":
        right.review_status = "accepted"
    elif difference == "confidence":
        right.confidence = 0.91
    elif difference == "perceptual_hash":
        right.perceptual_hash = "fedcba9876543210"
    elif difference == "alias_identity":
        right.aliases = ("TODDY CHOCOLATE 370G",)
    elif difference == "variant_sha":
        right.metadata["variant_sha256"] = ["d" * 64]
    elif difference == "association_status":
        right.metadata["association_status"] = "review"
    elif difference == "provenance":
        right.metadata["provenance"][0]["source_file"] = "standalone/other-product.png"
    elif difference == "standalone_flag":
        right.metadata["standalone"] = False
    else:  # pragma: no cover
        raise AssertionError(difference)

    rc, result, _, _ = _compare(monkeypatch, tmp_path, [left], [right])

    assert rc == 31
    assert result["pass"] is False
    assert result["semantic_signature_equal"] is False


def test_semantic_comparator_rejects_canonical_asset_count_difference(monkeypatch, tmp_path):
    left = _asset(tmp_path / "canonical-a.png")
    right_a = deepcopy(left)
    right_b = _asset(tmp_path / "canonical-b.png", product="ARROZ PATOSUL 5KG")
    right_b.metadata["sha256_full"] = "e" * 64
    right_b.metadata["sha256"] = "e" * 64

    rc, result, _, _ = _compare(monkeypatch, tmp_path, [left], [right_a, right_b])

    assert rc == 31
    assert result["canonical_equal"] is False
    assert result["pass"] is False


def test_semantic_comparator_rejects_physical_materialization_difference(monkeypatch, tmp_path):
    left = _asset(tmp_path / "physical.png")
    right = deepcopy(left)
    right.path = str(tmp_path / "missing-physical.png")

    rc, result, _, _ = _compare(monkeypatch, tmp_path, [left], [right])

    assert rc == 31
    assert result["semantic_signature_equal"] is True
    assert result["physical_equal"] is False
    assert result["pass"] is False


def test_semantic_comparator_rejects_catalog_coverage_difference(monkeypatch, tmp_path):
    left = _asset(tmp_path / "coverage.png")
    right = deepcopy(left)
    left_root = tmp_path / "left-library"
    right_root = tmp_path / "right-library"
    changed = deepcopy(BASE_COVERAGE)
    changed.update({"likely": 43, "missing": 468, "any_candidate": 52, "any_candidate_coverage_percent": 10.0})

    rc, result, _, _ = _compare(
        monkeypatch,
        tmp_path,
        [left],
        [right],
        coverage={str(left_root): BASE_COVERAGE, str(right_root): changed},
    )

    assert rc == 31
    assert result["semantic_signature_equal"] is True
    assert result["coverage_equal"] is False
    assert result["pass"] is False


def test_semantic_comparator_rejects_department_coverage_difference(monkeypatch, tmp_path):
    left = _asset(tmp_path / "department.png")
    right = deepcopy(left)
    left_root = tmp_path / "left-library"
    right_root = tmp_path / "right-library"
    changed = {"catalog_products": 520, "departments": [{"department": "mercearia", "total": 76}]}

    rc, result, _, _ = _compare(
        monkeypatch,
        tmp_path,
        [left],
        [right],
        departments={str(left_root): BASE_DEPARTMENTS, str(right_root): changed},
    )

    assert rc == 31
    assert result["semantic_signature_equal"] is True
    assert result["departments_equal"] is False
    assert result["pass"] is False
