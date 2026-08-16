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
                "mapping_image_coverage": 0.95,
                "mapping_group_coverage": 0.90,
                "blockers": 0,
                "warnings": 2,
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
