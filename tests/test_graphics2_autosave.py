from __future__ import annotations

from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.package import save_package


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


def test_save_if_changed_skips_unchanged_scene_and_honors_interval(tmp_path):
    now = [100.0]
    manager = AutosaveManager(
        tmp_path,
        generations=3,
        interval_seconds=30,
        clock=lambda: now[0],
    )
    document = GraphicsDocument(name="Campanha")

    first = manager.save_if_changed(document)
    assert first is not None
    assert first.exists()

    now[0] += 10
    document.metadata["revision"] = 1
    assert manager.save_if_changed(document) is None

    now[0] += 20
    second = manager.save_if_changed(document)
    assert second is not None
    assert second != first

    now[0] += 30
    assert manager.save_if_changed(document) is None
    assert len(manager.list_recovery_points(document.id)) == 2


def test_mark_current_state_prevents_immediate_redundant_autosave(tmp_path):
    now = [10.0]
    manager = AutosaveManager(tmp_path, clock=lambda: now[0])
    document = GraphicsDocument(name="Manual")
    manager.mark_current_state(document)

    now[0] += 31
    assert manager.save_if_changed(document) is None

    document.metadata["changed"] = True
    now[0] += 31
    assert manager.save_if_changed(document) is not None


def test_corrupt_newest_generation_does_not_hide_older_valid_recovery(tmp_path):
    manager = AutosaveManager(tmp_path, generations=3)
    document = GraphicsDocument(name="Recuperação")
    valid = manager.save(document)
    corrupt = valid.parent / "99999999T999999.999999Z.srscene"
    corrupt.write_bytes(b"not-a-scene")

    points = manager.list_recovery_points(document.id)
    assert len(points) == 1
    assert points[0].path == valid
    assert manager.latest(document.id).path == valid


def test_has_newer_recovery_compares_against_manual_project_and_clear_is_scoped(tmp_path):
    manager = AutosaveManager(tmp_path / "recovery")
    document = GraphicsDocument(name="Projeto")
    manual = tmp_path / "projeto.srscene"
    save_package(document, manual, embed_local_assets=False)
    manager.mark_current_state(document)

    document.metadata["revision"] = 2
    autosave = manager.save(document)
    manual_mtime = manual.stat().st_mtime_ns
    autosave_mtime = max(manual_mtime + 1, autosave.stat().st_mtime_ns)
    autosave.touch()

    # A recovery point exists independently from the user's explicit file.
    assert manager.latest(document.id) is not None
    assert manual.exists()

    removed = manager.clear(document.id)
    assert removed == 1
    assert manager.latest(document.id) is None
    assert manual.exists()
