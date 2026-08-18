from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json

from PIL import Image
import pytest

from srstudio.graphics2.reference_suite import (
    _render_performance,
    _top_impact_note,
    _top_suspect_note,
    load_reference_manifest,
    verify_reference_case,
)


def _write_image(path: Path, size=(120, 160)) -> str:
    Image.new("RGB", size, "white").save(path, quality=95)
    return sha256(path.read_bytes()).hexdigest()


def test_reference_manifest_maps_sparse_pptx_pages_and_verifies_identity(tmp_path):
    image = tmp_path / "page.jpg"
    digest = _write_image(image, (1229, 1536))
    manifest_path = tmp_path / "quinta.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": "Quinta Filé",
                "source": {"name": "quinta.pptx", "sha256": "a" * 64},
                "cases": [
                    {
                        "name": "grade principal",
                        "page": 13,
                        "file": image.name,
                        "sha256": digest,
                        "width": 1229,
                        "height": 1536,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = load_reference_manifest(manifest_path)
    assert manifest.name == "Quinta Filé"
    assert manifest.source_name == "quinta.pptx"
    assert manifest.cases[0].page == 13
    assert verify_reference_case(manifest.cases[0], tmp_path) == image.resolve()


def test_reference_manifest_rejects_duplicate_slide_mapping(tmp_path):
    manifest = tmp_path / "bad.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {"page": 1, "file": "a.png"},
                    {"page": 1, "file": "b.png"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicado"):
        load_reference_manifest(manifest)


def test_reference_case_rejects_changed_export(tmp_path):
    image = tmp_path / "page.jpg"
    _write_image(image)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "page": 0,
                        "file": image.name,
                        "sha256": "0" * 64,
                        "width": 120,
                        "height": 160,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    case = load_reference_manifest(manifest).cases[0]
    with pytest.raises(ValueError, match="SHA-256"):
        verify_reference_case(case, tmp_path)


def test_reference_suite_formats_top_scene_suspect_for_console() -> None:
    attribution = {
        "regions": [
            {
                "region_index": 1,
                "suspects": [
                    {
                        "node_id": "price_reais",
                        "name": "Preço principal",
                        "kind": "text",
                        "binding_role": "price_reais",
                    }
                ],
            }
        ]
    }

    assert _top_suspect_note(attribution) == " · provável price_reais: Preço principal"
    assert _top_suspect_note({"regions": [{"suspects": []}]}) == " · sem node SR Scene associado"
    assert _top_suspect_note({}) == ""


def test_reference_suite_formats_top_impact_category_for_console() -> None:
    impact = {
        "categories": [
            {
                "category": "TEXT",
                "priority": "P1",
                "estimated_percentage_points": 6.375,
                "impact_share": 0.72,
            }
        ]
    }

    assert _top_impact_note(impact) == " · impacto TEXT/P1: ~6.38 pp (72.0% do diff medido)"
    assert _top_impact_note({}) == ""


def test_reference_suite_summarizes_render_timings_without_threshold_coupling() -> None:
    summary = _render_performance([12.5, 25.0, 17.5])

    assert summary == {
        "total_ms": 55.0,
        "average_ms": pytest.approx(55.0 / 3.0),
        "minimum_ms": 12.5,
        "maximum_ms": 25.0,
    }
    assert _render_performance([]) == {
        "total_ms": 0,
        "average_ms": 0.0,
        "minimum_ms": 0.0,
        "maximum_ms": 0.0,
    }


def test_reference_suite_source_persists_scene_aware_worst_case() -> None:
    source = (Path(__file__).parents[1] / "src" / "srstudio" / "graphics2" / "reference_suite.py").read_text(encoding="utf-8")
    assert "attribute_fidelity_regions" in source
    assert "summarize_fidelity_impact" in source
    assert '"attribution_report"' in source
    assert '"impact_report"' in source
    assert "store_fidelity_triage" in source
    assert '"visual_fidelity_worst_case"' in source
    assert '"pptx_effect_mapping"' in source
    assert '"render_ms"' in source
    assert '"performance"' in source


def test_real_quinta_manifest_keeps_confirmed_slide_mapping():
    path = Path(__file__).parents[1] / "visual-fidelity" / "quinta-file-13-08-2026.json"
    manifest = load_reference_manifest(path)
    assert manifest.source_sha256 == "7c45cfa205c7e14af69e41c8d63b1c6a9d1a06df3cf9d0131ed612029884e536"
    assert [case.page for case in manifest.cases] == [13, 14, 11, 12]
    assert [case.file for case in manifest.cases] == [
        "1000255373.jpg",
        "1000255374.jpg",
        "1000255371.jpg",
        "1000255372.jpg",
    ]
