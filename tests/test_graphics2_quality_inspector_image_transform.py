from __future__ import annotations

from pathlib import Path

import srstudio.graphics2.qt_host as qt_host


def test_quality_inspector_surfaces_exact_image_transform_contracts():
    qml = (Path(qt_host.__file__).with_name("qml") / "QualityInspector.qml").read_text(encoding="utf-8")

    assert 'Label { text: "Transform. imagens"' in qml
    assert "gate.image_transform_coverage" in qml
    assert 'text: "Rotação/flip especial"' in qml
    assert "gate.image_transform_non_identity_contracts" in qml
    assert "gate.image_transform_non_identity_coverage" in qml
    assert "coverageColor(gate.image_transform_coverage)" in qml
    assert "coverageColor(gate.image_transform_non_identity_coverage)" in qml
