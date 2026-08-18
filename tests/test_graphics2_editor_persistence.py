from __future__ import annotations

from datetime import datetime, timezone
import os

from srstudio.graphics2.autosave import AutosaveManager, RecoveryPoint
from srstudio.graphics2.editor_persistence import (
    EditorPersistenceState,
    EditorRecentProject,
    EditorRecoveryJournal,
    document_digest,
    newer_recovery_point,
)
from srstudio.graphics2.model import GraphicsDocument


def test_dirty_state_tracks_save_and_autosave_by_document_content(tmp_path):
    document = GraphicsDocument(name="Campanha")
    state = EditorPersistenceState.for_document(
        document,
        saved_path=tmp_path / "campanha.srscene",
        already_saved=True,
    )

    assert not state.is_dirty(document)
    assert not state.needs_autosave(document)

    document.name = "Campanha alterada"
    changed_digest = document_digest(document)
    assert state.is_dirty(document)
    assert state.needs_autosave(document)

    state.mark_autosaved(changed_digest)
    assert state.is_dirty(document)
    assert not state.needs_autosave(document)

    state.mark_saved(changed_digest, tmp_path / "campanha-final.srscene")
    assert not state.is_dirty(document)
    assert not state.needs_autosave(document)
    assert state.saved_path == (tmp_path / "campanha-final.srscene").resolve()


def test_imported_or_new_document_starts_dirty_until_first_manual_save(tmp_path):
    document = GraphicsDocument(name="Novo")
    state = EditorPersistenceState.for_document(document, already_saved=False)

    assert state.is_dirty(document)
    assert state.needs_autosave(document)

    state.mark_saved(document, tmp_path / "novo.srscene")

    assert not state.is_dirty(document)


def test_newer_recovery_point_only_wins_when_newer_than_saved_project(tmp_path):
    manager = AutosaveManager(tmp_path / "autosave")
    document = GraphicsDocument(name="Campanha")
    saved = tmp_path / "campanha.srscene"
    saved.write_bytes(b"placeholder")

    manager.save(document)
    point = manager.latest(document.id)
    assert point is not None

    old_epoch = point.saved_at.timestamp() - 10
    os.utime(saved, (old_epoch, old_epoch))
    assert newer_recovery_point(manager, document, saved) == point

    future_epoch = datetime.now(timezone.utc).timestamp() + 120
    os.utime(saved, (future_epoch, future_epoch))
    assert newer_recovery_point(manager, document, saved) is None


def test_recovered_state_remains_dirty_against_manual_save(tmp_path):
    document = GraphicsDocument(name="Recovered")
    point_path = tmp_path / "recovery.srscene"
    point_path.write_bytes(b"marker")
    point = RecoveryPoint(
        path=point_path,
        document_id=document.id,
        document_name=document.name,
        saved_at=datetime.now(timezone.utc),
        size=point_path.stat().st_size,
    )

    state = EditorPersistenceState.for_document(
        document,
        saved_path=tmp_path / "saved.srscene",
        already_saved=True,
        recovered_from=point,
    )

    assert state.is_dirty(document)
    assert not state.needs_autosave(document)
    assert state.recovered_from == point


def test_recovery_journal_only_points_to_explicit_pending_session(tmp_path):
    manager = AutosaveManager(tmp_path / "autosave")
    document = GraphicsDocument(name="Sessão pendente")
    recovery_path = manager.save(document)
    journal = EditorRecoveryJournal(tmp_path / "autosave")
    source = tmp_path / "origem.srscene"
    source.write_bytes(b"saved-marker")

    journal.mark(document.id, recovery_path, source_path=source)

    current = journal.current()
    assert current is not None
    assert current.document_id == document.id
    assert current.recovery_path == recovery_path.resolve()
    assert current.source_path == source.resolve()
    assert journal.recovery_point(manager) == manager.latest(document.id)

    journal.clear(document.id)
    assert journal.current() is None


def test_recovery_journal_does_not_resume_missing_or_unrelated_pointer(tmp_path):
    manager = AutosaveManager(tmp_path / "autosave")
    document = GraphicsDocument(name="Outro")
    manager.save(document)
    journal = EditorRecoveryJournal(tmp_path / "autosave")

    missing = tmp_path / "missing.srscene"
    journal.mark(document.id, missing)

    assert journal.current() is None
    assert journal.recovery_point(manager) is None


def test_recent_project_is_separate_from_pending_recovery(tmp_path):
    root = tmp_path / "autosave"
    recent = EditorRecentProject(root)
    recovery = EditorRecoveryJournal(root)
    project = tmp_path / "campanha.srscene"
    project.write_bytes(b"project-marker")

    recent.mark(project, document_id="doc_123")

    current = recent.current()
    assert current is not None
    assert current.document_id == "doc_123"
    assert current.path == project.resolve()
    assert recovery.current() is None


def test_recent_project_ignores_non_project_files_and_missing_targets(tmp_path):
    recent = EditorRecentProject(tmp_path / "state")
    pptx = tmp_path / "modelo.pptx"
    pptx.write_bytes(b"pptx-marker")

    recent.mark(pptx, document_id="doc_ignored")
    assert recent.current() is None

    project = tmp_path / "campanha.srscene"
    project.write_bytes(b"project-marker")
    recent.mark(project, document_id="doc_real")
    project.unlink()

    assert recent.current() is None
