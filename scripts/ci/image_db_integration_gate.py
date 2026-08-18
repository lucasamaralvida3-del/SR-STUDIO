from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

from srstudio.images.association import normalize_product_name
from srstudio.images.lookup import ProductImageLookupService
from srstudio.images.safe_library import SafeImageLibrary

from image_db_phase3b import _canonical_sha, library_snapshot


EXPECTED_STANDALONE_SIZE = 48_848_012
EXPECTED_STANDALONE_SHA256 = "9c2f12d23aa827fa88124dcf82468daed42a05fb44df6ab8109e0b487dc384ff"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def standalone_gate(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.artifact_dir)
    verification = _read(artifact_dir / "standalone-asset-verification.json")
    manifest = _read(artifact_dir / "standalone-manifest.json")
    metrics = manifest["metrics"]
    checks = {
        "available": os.environ.get("STANDALONE_AVAILABLE") == "true",
        "validated": os.environ.get("STANDALONE_CORPUS_VALIDATED") == "true",
        "manifest_present": bool(os.environ.get("STANDALONE_MANIFEST")),
        "verified": verification.get("verified") is True,
        "download_complete": verification.get("download_complete") is True,
        "size_exact_reference": int(verification.get("actual_size") or 0) == EXPECTED_STANDALONE_SIZE,
        "sha256_exact_reference": str(verification.get("sha256") or "").lower() == EXPECTED_STANDALONE_SHA256,
        "zip_integrity": verification.get("zip_integrity") is True,
        "image_files_160": int(metrics.get("image_files") or -1) == 160,
        "valid_images_160": int(metrics.get("valid_images") or -1) == 160,
        "corrupt_images_zero": int(metrics.get("corrupt_images", -1)) == 0,
    }
    payload = {"verification": verification, "metrics": metrics, "checks": checks, "pass": all(checks.values())}
    _write(artifact_dir / "standalone-reference-gate.json", payload)
    return 0 if payload["pass"] else 61


def baseline_gate(args: argparse.Namespace) -> int:
    snapshot = _read(Path(args.snapshot))
    checks = {
        "canonical_1036": snapshot["canonical"] == 1036,
        "physical_1036": snapshot["physical"] == 1036,
        "missing_provenance_0": snapshot["missing_provenance"] == 0,
    }
    payload = {"snapshot": {key: value for key, value in snapshot.items() if key != "logical_rows"}, "checks": checks, "pass": all(checks.values())}
    _write(Path(args.output), payload)
    return 0 if payload["pass"] else 62


def idempotency_gate(args: argparse.Namespace) -> int:
    first = _read(Path(args.first))
    second = _read(Path(args.second))
    report = _read(Path(args.report))
    metrics = report.get("metrics", {})
    checks = {
        "canonical_1037": first["canonical"] == 1037 and second["canonical"] == 1037,
        "physical_1037": first["physical"] == 1037 and second["physical"] == 1037,
        "signature_unchanged": first["logical_signature_sha256"] == second["logical_signature_sha256"],
        "processed_zero": int(metrics.get("processed", -1)) == 0,
        "all_selected_skipped": int(metrics.get("skipped", -1)) == int(args.selected),
    }
    payload = {
        "first": {key: value for key, value in first.items() if key != "logical_rows"},
        "second": {key: value for key, value in second.items() if key != "logical_rows"},
        "second_metrics": metrics,
        "checks": checks,
        "pass": all(checks.values()),
    }
    _write(Path(args.output), payload)
    return 0 if payload["pass"] else 63


class _TinyLibrary:
    index_path = None

    def __init__(self, assets):
        self.assets = assets

    def all(self, *, status="", kind=""):
        values = self.assets
        if status:
            values = [item for item in values if item.review_status == status]
        return values


def _asset(asset_id: str, product_key: str, product_name: str, *, megapixels: float = 1.0, quality: float = 0.8):
    return SimpleNamespace(
        id=asset_id,
        product_key=product_key,
        product_name=product_name,
        aliases=(),
        kind="product",
        review_status="accepted",
        preferred=False,
        confidence=0.92,
        usage_count=0,
        megapixels=megapixels,
        mode="RGB",
        metadata={"quality_score": quality},
    )


def smoke(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.artifact_dir)
    library_root = Path(args.library)
    coverage = _read(artifact_dir / "after" / "coverage-catalog-520.json")
    audit = _read(artifact_dir / "after" / "library-audit.json")
    find_results = _read(artifact_dir / "after" / "find-image-results.json")
    idempotency = _read(artifact_dir / "idempotency.json")

    snapshot = library_snapshot(library_root)
    library = SafeImageLibrary(library_root)
    assets = list(library.all())
    logical_pairs = [
        (normalize_product_name(asset.product_name or asset.product_key), _canonical_sha(asset))
        for asset in assets
    ]
    duplicate_logical = sum(count - 1 for count in Counter(logical_pairs).values() if count > 1)

    exact = ProductImageLookupService(library).find_image("TOMATE PERA")
    missing = ProductImageLookupService(library).find_image("ARROZ VASCONCELOS 5KG")
    fuzzy = ProductImageLookupService(
        _TinyLibrary([_asset("m", "ENERGETICO MONSTER 473ML", "ENERGÉTICO MONSTER 473ML")])
    ).find_image("MONSTER 473ML")
    sku = ProductImageLookupService(
        _TinyLibrary(
            [
                _asset("370", "ACHOCOLATADO TODDY 370G", "TODDY 370G", megapixels=0.3, quality=0.32),
                _asset("750", "ACHOCOLATADO TODDY 750G", "TODDY 750G", megapixels=8.0, quality=0.99),
            ]
        )
    ).find_image("TODDY 370G")

    with tempfile.TemporaryDirectory() as temp:
        copied = Path(temp) / "library"
        shutil.copytree(library_root, copied)
        before = library_snapshot(copied)
        copied_library = SafeImageLibrary(copied)
        copied_library._save(copied_library._load())
        reloaded = library_snapshot(copied)
        save_reload_ok = (
            before["canonical"] == reloaded["canonical"]
            and before["logical_signature_sha256"] == reloaded["logical_signature_sha256"]
        )

    audit_metrics = audit.get("metrics", {})
    checks = {
        "load_index_1037": len(assets) == 1037,
        "canonical_1037": snapshot["canonical"] == 1037,
        "physical_1037": snapshot["physical"] == 1037,
        "accepted_11": snapshot["accepted"] == 11,
        "pending_1026": snapshot["pending"] == 1026,
        "rejected_0": snapshot["rejected"] == 0,
        "missing_provenance_0": snapshot["missing_provenance"] == 0 and int(audit_metrics.get("missing_provenance", 0)) == 0,
        "catalog_520": coverage.get("total") == 520,
        "auto_2": coverage.get("auto_approved") == 2,
        "likely_42": coverage.get("likely") == 42,
        "review_7": coverage.get("review_required") == 7,
        "missing_469": coverage.get("missing") == 469,
        "coverage_51": coverage.get("any_candidate") == 51,
        "coverage_9_8077": coverage.get("any_candidate_coverage_percent") == 9.8077,
        "exact_lookup": exact.best_match is not None and exact.best_match.asset.product_name == "TOMATE PERA",
        "fuzzy_lookup": fuzzy.best_match is not None and fuzzy.best_match.asset.id == "m",
        "product_without_image": missing.best_match is None,
        "sku_grammage_guard": sku.best_match is not None and sku.best_match.asset.id == "370" and all(item.asset.id != "750" for item in sku.alternatives),
        "negative_invariant_violations_0": find_results.get("negative_invariant_violations") == [],
        "duplicate_logical_associations_0": duplicate_logical == 0,
        "idempotency": idempotency.get("pass") is True,
        "save_reload": save_reload_ok,
    }
    payload = {
        "checks": checks,
        "pass": all(checks.values()),
        "negative_invariant_violations": len(find_results.get("negative_invariant_violations") or []),
        "duplicate_logical_associations": duplicate_logical,
        "coverage": coverage,
        "snapshot": {key: value for key, value in snapshot.items() if key != "logical_rows"},
        "sku_best": getattr(getattr(sku.best_match, "asset", None), "id", None),
        "sku_alternatives": [item.asset.id for item in sku.alternatives],
    }
    _write(artifact_dir / "integration-smoke.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["pass"] else 64


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    standalone = sub.add_parser("standalone")
    standalone.add_argument("--artifact-dir", required=True)
    standalone.set_defaults(func=standalone_gate)

    baseline = sub.add_parser("baseline")
    baseline.add_argument("--snapshot", required=True)
    baseline.add_argument("--output", required=True)
    baseline.set_defaults(func=baseline_gate)

    idem = sub.add_parser("idempotency")
    idem.add_argument("--first", required=True)
    idem.add_argument("--second", required=True)
    idem.add_argument("--report", required=True)
    idem.add_argument("--selected", required=True, type=int)
    idem.add_argument("--output", required=True)
    idem.set_defaults(func=idempotency_gate)

    final = sub.add_parser("smoke")
    final.add_argument("--library", required=True)
    final.add_argument("--artifact-dir", required=True)
    final.set_defaults(func=smoke)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
