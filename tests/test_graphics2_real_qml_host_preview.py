from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication

from srstudio.graphics2.qt_host import launch_qt_quick_editor, load_launch_context


_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_TEMPLATE = (
    _REPO_ROOT
    / "src"
    / "srstudio"
    / "assets"
    / "poster_templates"
    / "legacy"
    / "models"
    / "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"
)


def test_real_pptx_launches_complete_qt_quick_editor_offscreen():
    """Launch the actual host, bridge and all attached QML tools with a real SR PPTX."""

    context = load_launch_context(_REAL_TEMPLATE)
    assert context.source == _REAL_TEMPLATE.resolve()
    assert context.document.pages
    assert context.document.active_page.slots

    app = QGuiApplication.instance() or QGuiApplication(["sr-g2-preview-smoke"])
    # launch_qt_quick_editor reaches a real Qt event loop. Give the real QML
    # host enough time to create its window, bridge, image provider and context
    # tools before the smoke closes. A very short timer can fire during
    # processEvents() and leave exec() waiting for a second quit request.
    QTimer.singleShot(3000, app.quit)

    exit_code = launch_qt_quick_editor(
        context.document,
        graphics_api="software",
        launch_context=context,
    )

    assert exit_code == 0
