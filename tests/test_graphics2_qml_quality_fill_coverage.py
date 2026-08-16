from __future__ import annotations

from pathlib import Path

import srstudio.graphics2


def test_quality_inspector_surfaces_drawingml_fill_coverage_and_outset_risk():
    qml = (
        Path(srstudio.graphics2.__file__).with_name("qml") / "QualityInspector.qml"
    ).read_text(encoding="utf-8")

    assert 'text: "Cobertura fillRect"' in qml
    assert "gate.mapping_fill_rect_coverage" in qml
    assert 'text: "Outset de imagem"' in qml
    assert "gate.mapping_fill_outset_coverage" in qml
    assert "< 0.80 ? \"#B91C1C\"" in qml
    assert "< 0.95 ? \"#A16207\"" in qml
