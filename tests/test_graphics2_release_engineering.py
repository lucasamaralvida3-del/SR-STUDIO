from __future__ import annotations

from pathlib import Path

import srstudio
from srstudio.diagnostics.crash_guard import CrashGuard
from srstudio.graphics2 import ENGINE_VERSION
from srstudio.graphics2.entrypoint import diagnostics_root, main, version_string
from srstudio.graphics2.release_smoke import build_smoke_document


def test_release_smoke_document_is_small_portable_scene():
    document = build_smoke_document()

    assert document.schema == "srscene/2.0"
    assert len(document.pages) == 1
    assert document.active_page.width == 640
    assert document.active_page.height == 480
    assert len(document.active_page.nodes) == 2


def test_release_version_is_available_without_starting_qt(capsys):
    assert main(["--version"]) == 0
    output = capsys.readouterr().out.strip()
    assert srstudio.__version__ in output
    assert ENGINE_VERSION in output
    assert version_string() == output


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


def test_diagnostics_root_falls_back_when_preferred_path_is_not_writable(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked-diagnostics"
    blocked.write_text("not-a-directory", encoding="utf-8")
    monkeypatch.setenv("SR_STUDIO_G2_DIAGNOSTICS_ROOT", str(blocked))

    resolved = diagnostics_root()

    assert resolved != blocked
    assert resolved.is_dir()
    assert resolved.name == "diagnostics-g2"
