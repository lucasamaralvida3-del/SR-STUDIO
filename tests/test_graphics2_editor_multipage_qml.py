from __future__ import annotations

from pathlib import Path


_QML = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "srstudio"
    / "graphics2"
    / "qml"
    / "ProjectActions.qml"
)


def test_project_actions_exposes_complete_multipage_lifecycle():
    source = _QML.read_text(encoding="utf-8")

    assert '"name": "select_page"' in source
    assert '"name": "add_page"' in source
    assert '"name": "duplicate_page"' in source
    assert '"name": "remove_page"' in source
    assert "pageCount() > 1" in source
    assert "active_page_id" in source


def test_project_actions_keeps_save_and_export_actions_available():
    source = _QML.read_text(encoding="utf-8")

    assert "sceneBridge.saveProject()" in source
    assert "sceneBridge.saveSceneAs" in source
    assert "sceneBridge.dirty" in source
    assert "sceneBridge.autosaveBusy" in source
    assert "StandardKey.Save" in source
    assert "sceneBridge.exportPdf" in source
    assert "sceneBridge.exportPng" in source


def test_project_actions_exposes_standard_clipboard_shortcuts():
    source = _QML.read_text(encoding="utf-8")

    assert "StandardKey.Copy" in source
    assert "StandardKey.Cut" in source
    assert "StandardKey.Paste" in source
    assert '"name": "copy"' in source
    assert '"name": "cut"' in source
    assert '"name": "paste"' in source


def test_project_actions_blocks_close_when_recovery_cannot_be_written():
    source = _QML.read_text(encoding="utf-8")

    assert "function onClosing(close)" in source
    assert "sceneBridge.protectBeforeClose()" in source
    assert "close.accepted = false" in source


def test_project_actions_debounces_autosave_after_scene_changes():
    source = _QML.read_text(encoding="utf-8")

    assert "id: autosaveDebounce" in source
    assert "interval: 2500" in source
    assert "autosaveDebounce.restart()" in source
    assert "sceneBridge.autosaveIfNeeded()" in source
