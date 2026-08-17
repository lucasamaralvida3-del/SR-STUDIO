from __future__ import annotations

from pathlib import Path

import srstudio.graphics2.qt_host as qt_host


def test_quality_inspector_surfaces_exact_pptx_spacing_coverage():
    qml = (Path(qt_host.__file__).with_name("qml") / "QualityInspector.qml").read_text(encoding="utf-8")

    assert 'Label { text: "Espaço letras"' in qml
    assert "gate.mapping_letter_spacing_coverage" in qml
    assert 'Label { text: "Entrelinhas"' in qml
    assert "gate.mapping_line_spacing_coverage" in qml
    assert "coverageColor(gate.mapping_letter_spacing_coverage)" in qml
    assert "coverageColor(gate.mapping_line_spacing_coverage)" in qml
    assert 'return number < 0.80 ? "#B91C1C" : number < 0.95 ? "#A16207" : "#334155"' in qml
