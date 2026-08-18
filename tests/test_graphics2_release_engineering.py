from __future__ import annotations

from pathlib import Path

import srstudio
import srstudio.graphics2.entrypoint as entrypoint_module
from srstudio.diagnostics.crash_guard import CrashGuard
from srstudio.graphics2 import ENGINE_VERSION
from srstudio.graphics2.entrypoint import _writable_directory, diagnostics_root, main, version_string
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


def test_writable_directory_removes_probe_file(tmp_path):
    root = _writable_directory(tmp_path / "diagnostics")

    assert root.is_dir()
    assert list(root.glob(".srstudio-write-probe-*")) == []


def test_diagnostics_root_falls_back_when_preferred_path_is_not_writable(tmp_path, monkeypatch):
    preferred = tmp_path / "preferred"
    fallback = tmp_path / "fallback"
    monkeypatch.setenv("SR_STUDIO_G2_DIAGNOSTICS_ROOT", str(preferred))
    calls: list[Path] = []

    def fake_writable(candidate: Path) -> Path:
        calls.append(candidate)
        if candidate == preferred:
            raise PermissionError("preferred diagnostics path is read-only")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    monkeypatch.setattr(entrypoint_module, "_writable_directory", fake_writable)
    monkeypatch.setattr(entrypoint_module.tempfile, "gettempdir", lambda: str(tmp_path))

    resolved = diagnostics_root()

    assert resolved == fallback
    assert calls[0] == preferred
    assert len(calls) == 2
