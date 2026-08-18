from __future__ import annotations

from pathlib import Path
from threading import Thread

from srstudio.graphics2 import editor_entrypoint
from srstudio.graphics2.editor_persistence import EditorRecentProject, EditorRecoveryJournal
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.package import load_package as real_load_package
from srstudio.graphics2.package import save_package as real_save_package


def test_startup_prefers_pending_recovery_over_recent_project(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setattr(editor_entrypoint, "default_autosave_root", lambda: root)

    recent_file = tmp_path / "recent.srscene"
    recent_file.write_bytes(b"recent")
    EditorRecentProject(root).mark(recent_file, document_id="recent-doc")

    recovery_file = tmp_path / "recovery.srscene"
    recovery_file.write_bytes(b"recovery")
    EditorRecoveryJournal(root).mark("pending-doc", recovery_file)

    assert editor_entrypoint.resolve_startup_args([]) == []


def test_startup_uses_recent_project_when_no_pending_recovery(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setattr(editor_entrypoint, "default_autosave_root", lambda: root)
    project = tmp_path / "campanha.srscene"
    project.write_bytes(b"marker")
    EditorRecentProject(root).mark(project, document_id="doc_1")

    resolved = editor_entrypoint.resolve_startup_args(["--graphics-api", "software"])

    assert resolved[0] == str(project.resolve())
    assert resolved[1:] == ["--graphics-api", "software"]


def test_new_project_and_explicit_source_never_get_replaced_by_recent(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setattr(editor_entrypoint, "default_autosave_root", lambda: root)
    recent_file = tmp_path / "recent.srscene"
    recent_file.write_bytes(b"recent")
    EditorRecentProject(root).mark(recent_file, document_id="recent-doc")

    assert editor_entrypoint.resolve_startup_args(["--new-project"]) == ["--new-project"]

    explicit = tmp_path / "explicit.srscene"
    explicit.write_bytes(b"explicit")
    assert editor_entrypoint.resolve_startup_args([str(explicit)]) == [str(explicit)]


def test_manual_save_is_recent_only_after_verification_load_succeeds(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setattr(editor_entrypoint, "default_autosave_root", lambda: root)
    monkeypatch.setattr(editor_entrypoint.package_module, "load_package", real_load_package)
    editor_entrypoint.install_manual_save_recent_project_hook()

    document = GraphicsDocument(name="Entry point")
    manual_target = real_save_package(document, tmp_path / "manual.srscene")
    assert EditorRecentProject(root).current() is None
    failure: list[BaseException] = []

    def worker() -> None:
        try:
            verified = editor_entrypoint.package_module.load_package(manual_target)
            assert verified.id == document.id
        except BaseException as exc:  # pragma: no cover - surfaced below
            failure.append(exc)

    thread = Thread(target=worker, name="sr-graphics2-save")
    thread.start()
    thread.join()

    assert not failure
    recent = EditorRecentProject(root).current()
    assert recent is not None
    assert recent.document_id == document.id
    assert recent.path == Path(manual_target).resolve()


def test_failed_verification_never_promotes_file_to_recent(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setattr(editor_entrypoint, "default_autosave_root", lambda: root)
    monkeypatch.setattr(editor_entrypoint.package_module, "load_package", real_load_package)
    editor_entrypoint.install_manual_save_recent_project_hook()
    broken = tmp_path / "broken.srscene"
    broken.write_bytes(b"not-a-package")

    failure: list[BaseException] = []

    def worker() -> None:
        try:
            editor_entrypoint.package_module.load_package(broken)
        except BaseException as exc:
            failure.append(exc)

    thread = Thread(target=worker, name="sr-graphics2-save")
    thread.start()
    thread.join()

    assert failure
    assert EditorRecentProject(root).current() is None


def test_remember_explicit_saved_project_reads_real_srscene(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setattr(editor_entrypoint, "default_autosave_root", lambda: root)
    monkeypatch.setattr(editor_entrypoint.package_module, "load_package", real_load_package)
    document = GraphicsDocument(name="Aberto explicitamente")
    project = real_save_package(document, tmp_path / "explicit.srscene")

    editor_entrypoint.remember_explicit_saved_project([str(project)])

    recent = EditorRecentProject(root).current()
    assert recent is not None
    assert recent.document_id == document.id
    assert recent.path == Path(project).resolve()
