from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.quality import inspect_production_gate, store_visual_fidelity


def _healthy_document() -> GraphicsDocument:
    document = GraphicsDocument(name="Production Gate")
    page = document.active_page
    page.add_node(
        GraphicsNode(
            kind=NodeKind.RECT,
            transform=Transform(x=20, y=20, width=400, height=260),
            style={"fill": "#FFFFFF", "stroke": "#000000", "stroke_width": 1},
        )
    )
    document.metadata["graphics2_import_audit"] = {
        "confidence": 0.99,
        "errors": 0,
        "warnings": 0,
    }
    return document


def test_production_gate_allows_structurally_clean_document_before_golden_master():
    document = _healthy_document()
    report = inspect_production_gate(document, require_visual_fidelity=False)
    assert report.ready
    assert report.blockers == 0
    assert report.score >= 90


def test_release_gate_blocks_document_without_visual_golden_master():
    document = _healthy_document()
    report = inspect_production_gate(document, require_visual_fidelity=True)
    assert not report.ready
    assert any(issue.code == "VISUAL_FIDELITY_MISSING" for issue in report.issues)


def test_release_gate_accepts_passing_visual_result_and_persists_it():
    document = _healthy_document()
    store_visual_fidelity(
        document,
        {
            "passed": True,
            "metrics": {"score": 0.993, "pixel_pass_ratio": 0.98, "changed_ratio": 0.02},
        },
    )
    report = inspect_production_gate(document, require_visual_fidelity=True)
    assert report.ready
    assert report.visual_passed is True
    assert report.visual_score == 0.993
    assert document.metadata["visual_fidelity_last"]["passed"] is True


def test_gate_blocks_incomplete_embedded_font_extraction():
    document = _healthy_document()
    document.metadata["pptx_fidelity"] = {
        "fonts_declared": 2,
        "fonts_extracted": 1,
        "warnings": [],
    }
    report = inspect_production_gate(document, require_visual_fidelity=False)
    assert not report.ready
    assert report.embedded_fonts_declared == 2
    assert report.embedded_fonts_extracted == 1
    assert any(issue.code == "EMBEDDED_FONTS_INCOMPLETE" for issue in report.issues)


def test_gate_blocks_failed_visual_comparison_even_with_high_numeric_score():
    document = _healthy_document()
    store_visual_fidelity(
        document,
        {
            "passed": False,
            "metrics": {"score": 0.991, "pixel_pass_ratio": 0.94, "changed_ratio": 0.06},
        },
    )
    report = inspect_production_gate(document, require_visual_fidelity=True)
    assert not report.ready
    assert any(issue.code == "VISUAL_FIDELITY_FAILED" for issue in report.issues)
