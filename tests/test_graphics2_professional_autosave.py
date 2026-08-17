from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.professional_autosave import ProfessionalAutosaveController


def _controller(tmp_path: Path):
    document = GraphicsDocument(name="Autosave PRO")
    document.active_page.add_node(GraphicsNode(kind=NodeKind.TEXT, text="OFERTA"))
    session = GraphicsSession(document)
    controller = ProfessionalAutosaveController(
        session,
        root=tmp_path / "autosave",
        interval_seconds=1,
        generations=3,
    )
    return session, controller


def test_professional_autosave_tick_writes_recovery_outside_manual_project(tmp_path: Path):
    session, controller = _controller(tmp_path)
    manual = tmp_path / "manual.srscene"
    report = controller.tick(min_interval_seconds=0)

    assert report.saved
    assert report.document_id == session.document.id
    assert Path(report.path).exists()
    assert Path(report.path) != manual
    status = controller.status()
    assert status.available
    assert status.same_as_live
    assert not status.recoverable


def test_recovery_becomes_actionable_when_live_scene_diverges_and_is_undoable(tmp_path: Path):
    session, controller = _controller(tmp_path)
    controller.tick(min_interval_seconds=0)
    node_id = next(iter(session.page.nodes))
    session.page.node(node_id).text = "ALTERADO APÓS AUTOSAVE"

    status = controller.status()
    assert status.available
    assert status.recoverable
    assert not status.same_as_live

    applied = controller.recover_latest()
    assert applied.changed
    assert session.page.node(node_id).text == "OFERTA"
    assert session.undo()
    assert session.page.node(node_id).text == "ALTERADO APÓS AUTOSAVE"


def test_recover_latest_is_noop_when_autosave_matches_live_scene(tmp_path: Path):
    session, controller = _controller(tmp_path)
    controller.tick(min_interval_seconds=0)

    report = controller.recover_latest()

    assert not report.changed
    assert "estado atual" in report.message


def test_clear_removes_only_recovery_points(tmp_path: Path):
    session, controller = _controller(tmp_path)
    controller.tick(min_interval_seconds=0)
    manual = tmp_path / "manual.srscene"
    manual.write_bytes(b"manual-placeholder")

    removed = controller.clear()

    assert removed == 1
    assert controller.status().available is False
    assert manual.exists()
