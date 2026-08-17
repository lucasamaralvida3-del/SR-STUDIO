from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.qt_host import build_editor_diagnostics


def test_editor_diagnostics_exposes_gate_and_import_state_without_pyside():
    document = GraphicsDocument(name="Diagnóstico")
    document.metadata["graphics2_import_audit"] = {
        "confidence": 0.97,
        "errors": 0,
        "warnings": 1,
    }
    document.metadata["visual_fidelity_last"] = {
        "passed": True,
        "metrics": {"score": 0.995},
    }
    document.metadata["pptx_mapping_audit"] = {
        "page_count_match": True,
        "text_coverage": 0.98,
        "image_coverage": 0.96,
        "group_coverage": 0.90,
        "source_text_shapes": 10,
        "source_image_shapes": 5,
        "source_groups": 4,
    }

    diagnostics = build_editor_diagnostics(
        document,
        source="OFERTAS QUINTA FILÉ NOVO.pptx",
        graphics_api="d3d11",
    )

    assert diagnostics["production_gate"]["score"] >= 90
    assert diagnostics["production_gate"]["blockers"] == 0
    assert diagnostics["import_audit"]["confidence"] == 0.97
    assert diagnostics["visual_fidelity"]["passed"] is True
    assert diagnostics["pptx_mapping"]["image_coverage"] == 0.96
    assert diagnostics["graphics_api_requested"] == "d3d11"
    assert diagnostics["source"].endswith("OFERTAS QUINTA FILÉ NOVO.pptx")


def test_editor_diagnostics_prefers_launch_import_audit_snapshot():
    document = GraphicsDocument(name="Diagnóstico")
    document.metadata["graphics2_import_audit"] = {"confidence": 0.10, "errors": 1}
    explicit = {"confidence": 0.99, "errors": 0, "warnings": 0}

    diagnostics = build_editor_diagnostics(document, import_audit=explicit)

    assert diagnostics["import_audit"] == explicit
    assert diagnostics["import_audit"] is not explicit
