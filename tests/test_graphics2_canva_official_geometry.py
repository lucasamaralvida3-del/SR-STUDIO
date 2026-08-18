from __future__ import annotations

import json
from pathlib import Path

from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
from srstudio.graphics2.pptx_source_profile import (
    IntendedCanvasSize,
    PhysicalPageSize,
    PptxSourceProfile,
    apply_pptx_page_geometry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "visual-fidelity" / "g2-official-corpus-v1.json"
PHYSICAL = PhysicalPageSize(10_287_000, 12_852_400)


def test_official_canva_corpus_has_11_confirmed_1080x1350_pages_and_no_png_baseline() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))

    assert payload["canva_dimension_evidence"]["status"] == "11/11-confirmed"
    assert payload["canva_dimension_evidence"]["source"] == "direct-canva-connector"
    assert payload["canva_dimension_evidence"]["native_canvas"] == {"width": 1080, "height": 1350}
    assert payload["canva_dimension_evidence"]["official_png_count"] == 0
    assert payload["baseline_policy"]["thresholds"] is None
    assert payload["approved_cases"] == []

    expected_design_ids = {"DAHMLMj6EH8", "DAHMAeLZD3Q", "DAHMFY898gM"}
    assert {item["canva_design_id"] for item in payload["candidates"]} == expected_design_ids

    pages_checked = 0
    for candidate in payload["candidates"]:
        assert candidate["canva_native_canvas"] == {"width": 1080, "height": 1350}
        assert candidate["canva_dimension_evidence"] == "direct-canva-connector"
        profile = PptxSourceProfile(
            name="canva",
            confidence="reliable",
            design_id=candidate["canva_design_id"],
            physical_page_size=PHYSICAL,
            intended_canvas_size=IntendedCanvasSize(1080.0, 1350.0),
            evidence=["direct-canva-connector", "hash-locked-pptx"],
            fingerprint_matches=7,
        )
        for _slide_number in candidate["slide_numbers"]:
            page = GraphicsPage(width=1080.0, height=1080.0 * PHYSICAL.height_emu / PHYSICAL.width_emu)
            document = GraphicsDocument(pages=[page])
            assert apply_pptx_page_geometry(document, profile) is True
            assert page.width == 1080.0
            assert page.height == 1350.0
            assert page.metadata["physical_page_size"]["width_emu"] == 10_287_000
            assert page.metadata["physical_page_size"]["height_emu"] == 12_852_400
            pages_checked += 1

    assert pages_checked == 11
