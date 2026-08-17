from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.autosave import AutosaveManager, RecoveryPoint
from srstudio.graphics2.model import GraphicsDocument


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


def test_corrupt_generation_does_not_consume_valid_retention_slot(tmp_path):
    manager = AutosaveManager(tmp_path, generations=2)
    document = GraphicsDocument(name="Campanha")
    document.metadata["revision"] = 1
    first = manager.save(document)

    corrupt = first.parent / "99999999T999999.999999Z.srscene"
    corrupt.write_bytes(b"broken autosave")

    document.metadata["revision"] = 2
    manager.save(document)
    document.metadata["revision"] = 3
    manager.save(document)

    points = manager.list_recovery_points(document.id)
    assert len(points) == 2
    assert [manager.recover(point).metadata["revision"] for point in points] == [3, 2]
    assert corrupt.exists(), "arquivo inválido é preservado para diagnóstico, mas não conta na retenção"


def test_recover_rejects_recovery_point_from_other_document(tmp_path):
    manager = AutosaveManager(tmp_path)
    original = GraphicsDocument(name="Encarte A")
    path = manager.save(original)
    point = RecoveryPoint(
        path=path,
        document_id="doc_diferente",
        document_name="Encarte B",
        saved_at=manager.latest(original.id).saved_at,
        size=Path(path).stat().st_size,
    )

    with pytest.raises(ValueError, match="não pertence"):
        manager.recover(point)


def test_latest_skips_corrupt_newest_file(tmp_path):
    manager = AutosaveManager(tmp_path)
    document = GraphicsDocument(name="Campanha")
    valid = manager.save(document)
    corrupt = valid.parent / "99999999T999999.999999Z.srscene"
    corrupt.write_bytes(b"broken")

    latest = manager.latest(document.id)

    assert latest is not None
    assert latest.path == valid
