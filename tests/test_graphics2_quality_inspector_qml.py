from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.model import GraphicsDocument


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


def test_quality_inspector_surfaces_scene_aware_probable_cause_without_changing_gate():
    source = _source()
    assert "visual_fidelity_triage_last" in source
    assert "visual_fidelity_triage" in source
    assert "topTriageSuspect" in source
    assert "diagnostic_hint" in source
    assert "Causa provável" in source
    assert "triage.available" in source


def test_quality_inspector_surfaces_pptx_effect_inventory_for_golden_master_review():
    source = _source()
    assert "effectsSummary" in source
    assert "Efeitos PPTX" in source
    assert "Alpha DrawingML" in source
    assert "gate.pptx_advanced_effects" in source
    assert "gate.pptx_gradient_fills" in source
    assert "gate.pptx_shadows" in source
    assert "gate.pptx_alpha_modifiers" in source


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


def test_quality_inspector_qml_loads_offscreen_when_pyside_is_available():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    scene = GraphicsDocument(name="Quality Inspector Smoke").to_dict()
    scene["metadata"]["visual_fidelity_triage_last"] = {
        "available": True,
        "attribution": {
            "regions": [
                {
                    "region_index": 1,
                    "suspects": [
                        {
                            "node_id": "price_reais",
                            "name": "Preço reais",
                            "kind": "text",
                            "binding_role": "price_reais",
                            "score": 0.98,
                            "diagnostic_hint": "preço: revisar tipografia e baseline",
                        }
                    ],
                }
            ]
        },
    }
    scene["editor"] = {
        "diagnostics": {
            "production_gate": {
                "ready": False,
                "score": 87,
                "structural_score": 100,
                "import_confidence": 0.97,
                "visual_score": None,
                "visual_passed": None,
                "mapping_text_coverage": 0.99,
                "mapping_autofit_coverage": 1.0,
                "mapping_image_coverage": 0.95,
                "mapping_fill_rect_coverage": 1.0,
                "mapping_fill_outset_coverage": 1.0,
                "mapping_image_clip_coverage": 1.0,
                "mapping_group_coverage": 0.90,
                "pptx_advanced_effects": 4,
                "pptx_gradient_fills": 2,
                "pptx_shadows": 2,
                "pptx_alpha_modifiers": 7,
                "blockers": 0,
                "warnings": 3,
            },
            "graphics_api_requested": "auto",
        }
    }

    class _Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(scene, ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return "Quality smoke"

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "QualityInspector.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    assert engine.rootObjects(), "QualityInspector.qml não carregou; há erro de QML ou dependência."
