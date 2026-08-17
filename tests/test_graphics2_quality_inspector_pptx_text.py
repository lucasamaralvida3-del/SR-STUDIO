from __future__ import annotations

from pathlib import Path

import srstudio.graphics2.qt_host as qt_host


def test_quality_inspector_surfaces_pptx_autofit_audit_and_coverage():
    qml = (Path(qt_host.__file__).with_name("qml") / "QualityInspector.qml").read_text(encoding="utf-8")

    assert 'pptxFidelity = diagnostics.pptx_fidelity || ({})' in qml
    assert 'Label { text: "Auto-fit PPTX"' in qml
    assert 'pptxFidelity.shape_autofit_nodes' in qml
    assert 'pptxFidelity.normal_autofit_nodes' in qml
    assert 'pptxFidelity.no_autofit_nodes' in qml
    assert '"Forma " + shape + " · Texto " + normal + " · Sem " + none' in qml
    assert 'Label { text: "Cobertura auto-fit"' in qml
    assert 'gate.mapping_autofit_coverage' in qml
    assert 'mapping_autofit_coverage === undefined ? 1 : gate.mapping_autofit_coverage' in qml
