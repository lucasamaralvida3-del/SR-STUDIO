from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import srstudio.graphics2.qt_host as qt_host
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession


def _source() -> str:
    return (Path(qt_host.__file__).with_name("qml") / "ProjectActions.qml").read_text(encoding="utf-8")


def test_project_actions_exposes_save_recovery_pdf_png_and_busy_state():
    source = _source()
    assert "QtQuick.Dialogs" in source
    assert "sceneBridge.busy" in source
    assert "sceneBridge.saveSceneAs" in source
    assert "sceneBridge.recoverLatest" in source
    assert "sceneBridge.exportPdf" in source
    assert "sceneBridge.exportPng" in source
    assert "FileDialog.SaveFile" in source
    assert "*.srscene" in source
    assert "*.pdf" in source
    assert "*.png" in source
    assert "Restaurar o ponto de autosave mais recente" in source


def test_qt_host_runs_file_operations_and_autosave_on_safe_snapshots():
    source = Path(qt_host.__file__).read_text(encoding="utf-8")
    assert "def _snapshot_document" in source
    assert "GraphicsDocument.from_dict(session.document.to_dict())" in source
    assert 'threading.Thread(target=worker, name=f"sr-graphics2-{kind}"' in source
    assert 'threading.Thread(target=worker, name="sr-graphics2-autosave"' in source
    assert "fileJobDone = Signal(bool, str, str, str)" in source
    assert "autosaveDone = Signal(bool, str, str)" in source
    assert "QTimer" in source
    assert "AUTOSAVE_DELAY_MS = 1500" in source
    assert "embed_local_assets=True" in source
    assert "app.aboutToQuit.connect(bridge.flushAutosave)" in source
    assert "session.history.clear()" in source
    assert "save_package(snapshot, output, embed_local_assets=True)" in source
    assert "render_pdf(snapshot, output, dpi=600)" in source
    assert "render_png(snapshot, output, page_index=page_index, dpi=300)" in source
    assert 'qml_dir / "ProjectActions.qml"' in source


def test_autosave_root_is_stable_for_source_and_configurable(tmp_path, monkeypatch):
    monkeypatch.setenv("SR_STUDIO_G2_AUTOSAVE_ROOT", str(tmp_path / "autosaves"))
    source = tmp_path / "campanha.srscene"

    first = qt_host._autosave_root(source)
    second = qt_host._autosave_root(source)
    untitled = qt_host._autosave_root(None)

    assert first == second
    assert first.parent == tmp_path / "autosaves"
    assert untitled.parent == tmp_path / "autosaves"
    assert first != untitled


def test_document_digest_changes_with_real_scene_mutation():
    document = GraphicsDocument(name="Digest")
    before = qt_host._document_digest(document)
    document.metadata["revision"] = 1
    after = qt_host._document_digest(document)

    assert before != after
    assert after == qt_host._document_digest(GraphicsDocument.from_dict(document.to_dict()))


def test_qml_file_path_normalizes_local_url_and_suffix_when_pyside_is_available(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QUrl

    raw = QUrl.fromLocalFile(str(tmp_path / "meu projeto")).toString()
    normalized = qt_host._qml_file_path(raw, ".srscene", QUrl)
    assert normalized == (tmp_path / "meu projeto.srscene").resolve()

    already = qt_host._qml_file_path(str(tmp_path / "encarte.PDF"), ".pdf", QUrl)
    assert already == (tmp_path / "encarte.PDF").resolve()


def test_project_actions_qml_loads_offscreen_when_pyside_is_available():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument(name="Actions Smoke")))

    class _Bridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return "Actions smoke"

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return False

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            return router.dispatch_json(payload)

        @Slot(result=bool)
        def recoverLatest(self) -> bool:
            return False

        @Slot(str)
        def saveSceneAs(self, _path: str) -> None:
            pass

        @Slot(str)
        def exportPdf(self, _path: str) -> None:
            pass

        @Slot(str)
        def exportPng(self, _path: str) -> None:
            pass

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    bridge = _Bridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(qt_host.__file__).with_name("qml") / "ProjectActions.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    app.processEvents()
    assert engine.rootObjects(), "ProjectActions.qml não carregou; há erro no fluxo de salvar/exportar/recuperar."
