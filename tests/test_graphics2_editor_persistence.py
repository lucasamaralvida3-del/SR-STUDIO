from __future__ import annotations

from datetime import datetime, timezone
import os

from srstudio.graphics2.autosave import AutosaveManager, RecoveryPoint
from srstudio.graphics2.editor_persistence import (
    EditorPersistenceState,
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
