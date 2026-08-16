from __future__ import annotations

from pathlib import Path

import srstudio.graphics2.qt_host as qt_host


def _source() -> str:
    return (Path(qt_host.__file__).with_name("qml") / "QualityInspector.qml").read_text(encoding="utf-8")


def test_quality_inspector_consumes_live_editor_diagnostics():
    source = _source()
    assert "scene.editor.diagnostics" in source
    assert "production_gate" in source
    assert "import_audit" in source
    assert "visual_fidelity" in source
    assert "pptx_mapping" in source
    assert "gate.structural_score" in source
    assert "gate.import_confidence" in source
    assert "gate.visual_score" in source
    assert "gate.mapping_text_coverage" in source
    assert "gate.mapping_image_coverage" in source
    assert "gate.mapping_group_coverage" in source


def test_quality_inspector_surfaces_blockers_warnings_and_gpu():
    source = _source()
    assert "Production Gate aprovado" in source
    assert "Production Gate bloqueado" in source
    assert "bloqueio(s)" in source
    assert "aviso(s)" in source
    assert "graphics_api_requested" in source


def test_host_attaches_both_contextual_qml_tools():
    source = Path(qt_host.__file__).read_text(encoding="utf-8")
    assert '_attach_context_qml_tool(' in source
    assert 'qml_dir / "ImageInspector.qml"' in source
    assert 'qml_dir / "QualityInspector.qml"' in source
