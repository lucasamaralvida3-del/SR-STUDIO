from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from srstudio.graphics2.export_output import ExportValidationError, export_raster_batch
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform


def _document(page_count: int = 3) -> GraphicsDocument:
    document = GraphicsDocument(name="Batch SR")
    first = document.pages[0]
    first.width = 100
    first.height = 125
    first.background = "#FFFFFF"
    document.pages = [first]
    for index in range(1, page_count):
        page = document.add_page()
        page.width = 100
        page.height = 125
        page.background = f"#{index * 40:02X}3366"
    document.active_page_id = document.pages[0].id
    return document


def _inject_missing_image(document: GraphicsDocument, page_index: int, missing: Path) -> None:
    document.pages[page_index].add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            transform=Transform(x=0, y=0, width=80, height=80),
            metadata={"source_url": str(missing.resolve())},
        )
    )


def test_successful_batch_publishes_complete_set_and_final_paths(tmp_path):
    document = _document(3)
    progress: list[tuple[int, int, str]] = []

    report = export_raster_batch(
        document,
        tmp_path,
        raster_format="png",
        target_width=100,
        progress=lambda done, total, item: progress.append((done, total, item.output.name)),
    )

    expected = ["Batch_SR_p001.png", "Batch_SR_p002.png", "Batch_SR_p003.png"]
    assert report.ok
    assert [item.output.name for item in report.outputs] == expected
    assert [path.name for path in sorted(tmp_path.glob("*.png"))] == expected
    assert progress == [(1, 3, expected[0]), (2, 3, expected[1]), (3, 3, expected[2])]
    assert not list(tmp_path.glob(".sr-g2-export-*.tmp"))


def test_middle_page_render_failure_publishes_no_partial_batch(tmp_path):
    document = _document(3)
    _inject_missing_image(document, 1, tmp_path / "missing-page-2.png")

    with pytest.raises(ExportValidationError, match="recurso obrigatório"):
        export_raster_batch(document, tmp_path, raster_format="png", target_width=100)

    assert not list(tmp_path.glob("*.png"))
    assert not list(tmp_path.glob(".sr-g2-export-*.tmp"))


def test_middle_page_failure_preserves_previous_complete_batch(tmp_path):
    document = _document(3)
    expected = [tmp_path / f"Batch_SR_p{index:03d}.png" for index in range(1, 4)]
    for index, path in enumerate(expected, start=1):
        path.write_bytes(f"previous-{index}".encode("ascii"))
    before = {path.name: path.read_bytes() for path in expected}
    _inject_missing_image(document, 1, tmp_path / "missing-page-2.png")

    with pytest.raises(ExportValidationError):
        export_raster_batch(document, tmp_path, raster_format="png", target_width=100, overwrite=True)

    assert {path.name: path.read_bytes() for path in expected} == before


def test_overwrite_false_rejects_entire_batch_before_render(tmp_path):
    document = _document(3)
    existing = tmp_path / "Batch_SR_p002.png"
    existing.write_bytes(b"keep")

    with pytest.raises(FileExistsError, match="Batch não sobrescrito"):
        export_raster_batch(document, tmp_path, raster_format="png", target_width=100, overwrite=False)

    assert existing.read_bytes() == b"keep"
    assert not (tmp_path / "Batch_SR_p001.png").exists()
    assert not (tmp_path / "Batch_SR_p003.png").exists()


def test_publish_failure_rolls_back_pages_already_published(monkeypatch, tmp_path):
    from srstudio.graphics2 import export_batch

    document = _document(3)
    real_replace = export_batch._atomic_replace
    injected = {"done": False}

    def flaky_replace(source, target):
        source_path = Path(source)
        target_path = Path(target)
        is_staged_page = source_path.parent.name.startswith(".sr-g2-export-")
        if is_staged_page and target_path.name == "Batch_SR_p002.png" and not injected["done"]:
            injected["done"] = True
            raise PermissionError("simulated locked destination")
        return real_replace(source, target)

    monkeypatch.setattr(export_batch, "_atomic_replace", flaky_replace)

    with pytest.raises(OSError, match="Não foi possível publicar página do batch"):
        export_raster_batch(document, tmp_path, raster_format="png", target_width=100)

    assert injected["done"] is True
    assert not list(tmp_path.glob("Batch_SR_p*.png"))
    assert not list(tmp_path.glob(".sr-g2-export-*.tmp"))
