from __future__ import annotations

from pathlib import Path

from srstudio.diagnostics.crash_guard import CrashGuard
from srstudio.graphics2.entrypoint import diagnostics_root
from srstudio.graphics2.release_smoke import build_smoke_document


def test_release_smoke_document_is_small_portable_scene():
    document = build_smoke_document()

    assert document.schema == "srscene/2.0"
    assert len(document.pages) == 1
    assert document.active_page.width == 640
    assert document.active_page.height == 480
    assert len(document.active_page.nodes) == 2


def test_crash_guard_records_release_context(tmp_path):
    guard = CrashGuard(tmp_path, version="srstudio=test; graphics2=test")
    try:
        raise RuntimeError("release-smoke-failure")
    except RuntimeError as exc:
        report = guard.capture(
            type(exc),
            exc,
            exc.__traceback__,
            "C:/projects/test.srscene",
            action="export-pdf",
            module="srstudio.graphics2.qt_renderer",
        )

    assert report.action == "export-pdf"
    assert report.module == "srstudio.graphics2.qt_renderer"
    assert report.project_path.endswith("test.srscene")
    assert "release-smoke-failure" in report.traceback
    assert guard.last_report() == report


def test_diagnostics_root_is_independent_from_working_directory(tmp_path, monkeypatch):
    configured = tmp_path / "diagnostics"
    elsewhere = tmp_path / "unrelated-cwd"
    elsewhere.mkdir()
    monkeypatch.setenv("SR_STUDIO_G2_DIAGNOSTICS_ROOT", str(configured))
    monkeypatch.chdir(elsewhere)

    resolved = diagnostics_root()

    assert resolved == configured
    assert resolved.is_dir()
    assert resolved != Path.cwd()
