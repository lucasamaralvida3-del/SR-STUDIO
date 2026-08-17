from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.quality import inspect_production_gate


def _report(*, source=10, non_identity=1, exact=10, exact_non_identity=1):
    return {
        "source_contracts": source,
        "non_identity_contracts": non_identity,
        "mapped_contracts": exact,
        "exact_contracts": exact,
        "exact_non_identity_contracts": exact_non_identity,
        "corrected_contracts": 0,
        "deferred_group_contracts": 0,
        "coverage": 1.0 if source == 0 else exact / source,
        "non_identity_coverage": 1.0 if non_identity == 0 else exact_non_identity / non_identity,
        "issues": [],
    }


def test_gate_blocks_severe_exact_image_transform_loss():
    document = GraphicsDocument(name="image transform loss")
    document.metadata["pptx_image_transform_recovery"] = _report(source=10, non_identity=2, exact=5, exact_non_identity=1)

    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert gate.image_transform_coverage == 0.5
    assert gate.image_transform_non_identity_coverage == 0.5
    assert gate.image_transform_non_identity_contracts == 2
    assert gate.score <= 50
    assert not gate.ready
    codes = {issue.code for issue in gate.issues}
    assert "PPTX_IMAGE_TRANSFORM_COVERAGE_FAILED" in codes
    assert "PPTX_IMAGE_TRANSFORM_NON_IDENTITY_FAILED" in codes


def test_gate_does_not_dilute_one_missing_special_rotation_in_many_identity_images():
    document = GraphicsDocument(name="special rotation lost")
    # Cobertura global perfeita, mas o único contrato visualmente especial
    # continua não comprovado. Ele precisa bloquear sozinho.
    document.metadata["pptx_image_transform_recovery"] = _report(source=31, non_identity=1, exact=31, exact_non_identity=0)

    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert gate.image_transform_coverage == 1.0
    assert gate.image_transform_non_identity_coverage == 0.0
    assert gate.score == 0
    assert any(issue.code == "PPTX_IMAGE_TRANSFORM_NON_IDENTITY_FAILED" for issue in gate.issues)


def test_gate_accepts_complete_image_transform_contracts():
    document = GraphicsDocument(name="image transforms complete")
    document.metadata["pptx_image_transform_recovery"] = _report(source=31, non_identity=3, exact=31, exact_non_identity=3)

    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert gate.image_transform_coverage == 1.0
    assert gate.image_transform_non_identity_coverage == 1.0
    assert gate.image_transform_non_identity_contracts == 3
    assert not any(issue.code.startswith("PPTX_IMAGE_TRANSFORM_") for issue in gate.issues)
