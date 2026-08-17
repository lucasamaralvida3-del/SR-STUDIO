from __future__ import annotations

from pathlib import Path


def test_project_actions_exposes_multipage_save_and_export_controls():
    qml = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "srstudio"
        / "graphics2"
        / "qml"
        / "ProjectActions.qml"
    ).read_text(encoding="utf-8")

    assert '"name": "add_page"' in qml
    assert '"name": "duplicate_page"' in qml
    assert 'text: "+ Página"' in qml
    assert 'text: "Duplicar pág."' in qml

    # A evolução multipágina não pode remover o fluxo já aprovado de projeto.
    assert "sceneBridge.saveSceneAs" in qml
    assert "sceneBridge.exportPdf" in qml
    assert "sceneBridge.exportPng" in qml
    assert "enabled: !sceneBridge.busy" in qml
