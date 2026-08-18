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

    assert "sceneBridge.saveSceneAs" in source
    assert "sceneBridge.exportPdf" in source
    assert "sceneBridge.exportPng" in source
