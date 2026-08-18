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
from srstudio.graphics2.model import AssetRef, GraphicsDocument, GraphicsNode, NodeKind, Transform


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


def test_document_digest_ignores_package_extraction_transport_only():
    stored = GraphicsDocument(name="Com imagem")
    asset = AssetRef(
        id="asset_produto",
        kind="image",
        source="assets/asset_produto.png",
        mime="image/png",
        sha256="abc123",
        embedded=True,
    )
    stored.add_asset(asset)
    node = GraphicsNode(
        id="node_produto",
        kind=NodeKind.IMAGE,
        asset_id=asset.id,
        transform=Transform(x=10, y=20, width=200, height=180),
    )
    stored.active_page.add_node(node)
    stored.metadata["embedded_fonts"] = [
        {
            "family": "SR Font",
            "style": "regular",
            "sha256": "font123",
            "extracted_path": "fonts/000-sr.ttf",
            "embedded": True,
        }
    ]

    extracted = GraphicsDocument.from_dict(stored.to_dict())
    extracted.assets[asset.id].source = "C:/cache/runtime/asset_produto.png"
    extracted.assets[asset.id].embedded = False
    extracted.active_page.nodes[node.id].metadata["bound_image_source"] = "C:/cache/runtime/asset_produto.png"
    extracted.active_page.nodes[node.id].metadata["package_asset_extracted"] = True
    extracted.metadata["embedded_fonts"][0]["extracted_path"] = "C:/cache/runtime/fonts/sr.ttf"
    extracted.metadata["embedded_fonts"][0]["embedded"] = False

    assert document_digest(extracted) == document_digest(stored)


def test_document_digest_still_changes_when_asset_content_changes():
    first = GraphicsDocument(name="Imagem")
    first.add_asset(AssetRef(id="asset_1", source="one.png", sha256="hash-one"))
    second = GraphicsDocument.from_dict(first.to_dict())
    second.assets["asset_1"].source = "two.png"
    second.assets["asset_1"].sha256 = "hash-two"

    assert document_digest(second) != document_digest(first)


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

    journal.mark(
        document.id,
        recovery_path,
        source_path=source,
        base_saved_digest="digest-base",
    )

    current = journal.current()
    assert current is not None
    assert current.document_id == document.id
    assert current.recovery_path == recovery_path.resolve()
    assert current.source_path == source.resolve()
    assert current.base_saved_digest == "digest-base"
    assert journal.recovery_point(manager) == manager.latest(document.id)

    journal.clear(document.id)
    assert journal.current() is None


def test_recovery_journal_reads_legacy_pointer_without_base_digest(tmp_path):
    manager = AutosaveManager(tmp_path / "autosave")
    document = GraphicsDocument(name="Legado")
    recovery_path = manager.save(document)
    journal = EditorRecoveryJournal(tmp_path / "autosave")

    journal.mark(document.id, recovery_path)

    current = journal.current()
    assert current is not None
    assert current.base_saved_digest is None


def test_recovery_journal_can_record_pre_first_save_empty_base_digest(tmp_path):
    manager = AutosaveManager(tmp_path / "autosave")
    document = GraphicsDocument(name="Novo ainda não salvo")
    recovery_path = manager.save(document)
    journal = EditorRecoveryJournal(tmp_path / "autosave")

    journal.mark(document.id, recovery_path, base_saved_digest="")

    current = journal.current()
    assert current is not None
    assert current.base_saved_digest == ""


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
