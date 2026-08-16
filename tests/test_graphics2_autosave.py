from __future__ import annotations

from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.model import GraphicsDocument


def test_autosave_keeps_generations_and_recovers(tmp_path):
    manager = AutosaveManager(tmp_path, generations=2); document = GraphicsDocument(name="Campanha")
    for index in range(3): document.metadata["revision"] = index; manager.save(document)
    points = manager.list_recovery_points(document.id); assert len(points) == 2; restored = manager.recover(points[0]); assert restored.id == document.id; assert restored.name == "Campanha"; assert restored.metadata["revision"] == 2
