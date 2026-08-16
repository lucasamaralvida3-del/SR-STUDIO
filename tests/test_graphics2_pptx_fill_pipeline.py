from __future__ import annotations

from srstudio.core.models import Page, StudioProject
from srstudio.graphics2.import_bridge import from_imported_project
from srstudio.graphics2.image_fill import drawingml_fill_destination, has_drawingml_fill_rect
from srstudio.graphics2.model import NodeKind
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.reader import PptxElement


def _converted_image(tmp_path, fill_rect: dict) -> dict:
    image = tmp_path / "produto.png"
    image.write_bytes(b"fake-image")
    source = PptxElement(
        "image",
        x=100,
        y=200,
        width=400,
        height=300,
        media_path=str(image),
        name="Canva Photo",
        metadata={
            "fill_rect": fill_rect,
            "picture_fill": True,
            "crop": {},
            "z_index": 7,
        },
    )
    converted = UnifiedImportPipeline._pptx_element(source, 1000, 1000, 1000, 1000)
    assert converted is not None
    return converted


def _graphics_node(element: dict):
    project = StudioProject()
    page = Page(name="PPTX", width=1000, height=1000)
    page.elements = [element]
    project.pages = [page]
    document = from_imported_project(project)
    return next(node for node in document.active_page.nodes.values() if node.kind is NodeKind.IMAGE)


def test_explicit_zero_fill_rect_survives_pipeline_and_graphics_bridge(tmp_path):
    converted = _converted_image(tmp_path, {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0})

    assert converted["fill_rect"] == {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}
    assert converted["image_fit"] == "cover"
    node = _graphics_node(converted)
    assert node.style["fill_rect"] == {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}
    assert has_drawingml_fill_rect(node.style["fill_rect"])


def test_negative_canva_fill_outset_survives_pipeline_without_geometry_rewrite(tmp_path):
    source_fill = {"l": -0.30959, "t": 0.0, "r": -0.30437, "b": 0.0}
    converted = _converted_image(tmp_path, source_fill)
    before = (converted["x"], converted["y"], converted["width"], converted["height"])

    node = _graphics_node(converted)

    assert node.style["fill_rect"] == source_fill
    assert (node.transform.x, node.transform.y, node.transform.width, node.transform.height) == before
    destination = drawingml_fill_destination(node.transform.width, node.transform.height, node.style["fill_rect"])
    assert destination.x < 0
    assert destination.width > node.transform.width
