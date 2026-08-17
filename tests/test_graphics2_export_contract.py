from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.export_contract import run_snapshot_export, snapshot_document
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.scene_fingerprint import fingerprint_document


def _document():
    document = GraphicsDocument(name="Export seguro")
    document.active_page.add_node(
        GraphicsNode(
            kind=NodeKind.TEXT,
            text="OFERTA",
            transform=Transform(x=10, y=20, width=200, height=60),
        )
    )
    return document


def test_snapshot_document_is_independent_but_structurally_equivalent():
    document = _document()
    clone = snapshot_document(document)

    assert clone is not document
    assert clone.active_page is not document.active_page
    assert fingerprint_document(clone).sha256 == fingerprint_document(document).sha256

    clone.active_page.nodes[next(iter(clone.active_page.nodes))].text = "ALTERADO"
    assert fingerprint_document(clone).sha256 != fingerprint_document(document).sha256


def test_run_snapshot_export_allows_exporter_to_mutate_only_snapshot(tmp_path: Path):
    document = _document()
    original = document.to_dict()
    target = tmp_path / "preview.fake"

    def exporter(snapshot: GraphicsDocument, output: Path):
        snapshot.metadata["temporary_export_diagnostic"] = True
        snapshot.active_page.nodes[next(iter(snapshot.active_page.nodes))].text = "EXPORT SNAPSHOT"
        output.write_text("ok", encoding="utf-8")
        return output

    report = run_snapshot_export(document, target, exporter)

    assert report.safe
    assert report.original_unchanged
    assert report.snapshot_changed_by_exporter
    assert report.output == target
    assert target.read_text(encoding="utf-8") == "ok"
    assert document.to_dict() == original


def test_run_snapshot_export_preserves_live_scene_when_exporter_fails(tmp_path: Path):
    document = _document()
    before = fingerprint_document(document).sha256

    def exporter(snapshot: GraphicsDocument, output: Path):
        snapshot.name = "temporário"
        raise ValueError("falha simulada")

    try:
        run_snapshot_export(document, tmp_path / "fail.fake", exporter)
    except ValueError as exc:
        assert str(exc) == "falha simulada"
    else:
        raise AssertionError("exporter deveria falhar")

    assert fingerprint_document(document).sha256 == before
