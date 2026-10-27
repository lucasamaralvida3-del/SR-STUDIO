from __future__ import annotations

from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.model import GraphicsDocument


def test_same_clock_tick_never_overwrites_a_recovery_generation(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import srstudio.graphics2.autosave as autosave
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(autosave, "datetime", FrozenDatetime)
    manager = AutosaveManager(tmp_path, generations=2)
    document = GraphicsDocument(name="Fast saves")
    paths = []
    for revision in range(4):
        document.metadata["revision"] = revision
        paths.append(manager.save(document))
    assert len(set(paths)) == 4
    latest = manager.latest(document.id)
    assert manager.recover(latest).metadata["revision"] == 3
    latest.path.write_bytes(b"truncated")
    previous = manager.latest(document.id)
    assert manager.recover(previous).metadata["revision"] == 2


def test_autosave_keeps_generations_and_recovers(tmp_path):
    manager = AutosaveManager(tmp_path, generations=2)
    document = GraphicsDocument(name="Campanha")
    for index in range(3):
        document.metadata["revision"] = index
        manager.save(document)
    points = manager.list_recovery_points(document.id)
    assert len(points) == 2
    restored = manager.recover(points[0])
    assert restored.id == document.id
    assert restored.name == "Campanha"
    assert restored.metadata["revision"] == 2


def test_latest_any_returns_most_recent_recovery_across_documents(tmp_path):
    manager = AutosaveManager(tmp_path, generations=3)
    first = GraphicsDocument(name="Primeiro")
    second = GraphicsDocument(name="Segundo")

    manager.save(first)
    second.metadata["revision"] = 7
    manager.save(second)

    latest = manager.latest_any()
    assert latest is not None
    assert latest.document_id == second.id
    restored = manager.recover(latest)
    assert restored.metadata["revision"] == 7


def test_autosave_can_embed_local_assets_for_crash_recovery(tmp_path):
    manager = AutosaveManager(tmp_path, embed_local_assets=True)
    document = GraphicsDocument(name="Asset Safe")

    saved = manager.save(document)

    assert saved.is_file()
    assert manager.embed_local_assets is True
    latest = manager.latest(document.id)
    assert latest is not None
    restored = manager.recover(latest, extract_assets_to=tmp_path / "restored-assets")
    assert restored.id == document.id
