from __future__ import annotations

import os

from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.editor_persistence import document_digest
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.package import save_package
from srstudio.graphics2 import qt_host


def test_saved_project_recovers_newer_valid_autosave(tmp_path, monkeypatch):
    autosave_root = tmp_path / "autosave"
    monkeypatch.setattr(qt_host, "default_autosave_root", lambda: autosave_root)

    saved = GraphicsDocument(name="Campanha")
    saved.metadata["revision"] = "manual"
    project = save_package(saved, tmp_path / "campanha.srscene")
    manual_digest = document_digest(saved)

    recovered_source = GraphicsDocument.from_dict(saved.to_dict())
    recovered_source.metadata["revision"] = "autosave"
    manager = AutosaveManager(autosave_root)
    manager.save(recovered_source)
    point = manager.latest(saved.id)
    assert point is not None

    old_epoch = point.saved_at.timestamp() - 30
    os.utime(project, (old_epoch, old_epoch))

    context = qt_host.load_launch_context(project)

    assert context.recovered_from is not None
    assert context.recovered_from.path == point.path
    assert context.document.metadata["revision"] == "autosave"
    assert context.saved_digest == manual_digest
    assert document_digest(context.document) != context.saved_digest


def test_saved_project_does_not_replace_newer_manual_save_with_old_autosave(tmp_path, monkeypatch):
    autosave_root = tmp_path / "autosave"
    monkeypatch.setattr(qt_host, "default_autosave_root", lambda: autosave_root)

    document = GraphicsDocument(name="Campanha")
    project = save_package(document, tmp_path / "campanha.srscene")
    manager = AutosaveManager(autosave_root)
    manager.save(document)
    point = manager.latest(document.id)
    assert point is not None

    future_epoch = point.saved_at.timestamp() + 30
    os.utime(project, (future_epoch, future_epoch))

    context = qt_host.load_launch_context(project)

    assert context.recovered_from is None
    assert context.document.id == document.id
    assert document_digest(context.document) == context.saved_digest


def test_qt_host_wires_periodic_and_shutdown_autosave_contract():
    source = qt_host.__file__
    text = open(source, encoding="utf-8").read()

    assert "AUTOSAVE_INTERVAL_MS = 45_000" in text
    assert "autosave_timer.timeout.connect(bridge.autosaveIfNeeded)" in text
    assert "app.aboutToQuit.connect(protect_unsaved_on_quit)" in text
    assert 'qml_dir / "PageInspector.qml"' in text
    assert "verified = load_package(final)" in text
