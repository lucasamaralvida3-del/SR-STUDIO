from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from srstudio.graphics2.image_fill import drawingml_fill_destination
from srstudio.graphics2.model import GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.pptx_fidelity import PptxFidelityReport, _custom_path_spec, _enrich_page
from srstudio.graphics2.pptx_fill_rect import _rect_percent


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _picture_fill_custom_shape() -> tuple[ET.Element, ET.Element]:
    """Minimal Canva-like picture fill: non-rect custGeom + negative fillRect."""

    root = ET.fromstring(
        f"""
<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="7" name="Masked Photo"/></p:nvSpPr>
      <p:spPr>
        <a:custGeom>
          <a:pathLst>
            <a:path w="100000" h="100000">
              <a:moveTo><a:pt x="0" y="0"/></a:moveTo>
              <a:lnTo><a:pt x="100000" y="0"/></a:lnTo>
              <a:lnTo><a:pt x="50000" y="100000"/></a:lnTo>
              <a:close/>
            </a:path>
          </a:pathLst>
        </a:custGeom>
        <a:blipFill>
          <a:blip/>
          <a:stretch><a:fillRect l="-25000" t="-10000" r="-30000" b="-5000"/></a:stretch>
        </a:blipFill>
      </p:spPr>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""
    )
    shape = root.find(f".//{{{P_NS}}}sp")
    assert shape is not None
    return root, shape


def _image_node() -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Masked Photo",
        transform=Transform(x=10.0, y=20.0, width=200.0, height=100.0),
        metadata={"source_name": "Masked Photo"},
    )


def test_minimal_picture_fill_fixture_preserves_nonrect_custgeom_and_negative_fillrect_contract() -> None:
    _root, shape = _picture_fill_custom_shape()
    path_spec = _custom_path_spec(shape)
    fill_rect_node = shape.find(f".//{{{A_NS}}}fillRect")

    assert path_spec is not None
    assert [command["op"] for command in path_spec["paths"][0]["commands"]] == ["M", "L", "L", "Z"]
    assert fill_rect_node is not None
    fill_rect = _rect_percent(fill_rect_node)
    assert fill_rect == {"l": -0.25, "t": -0.1, "r": -0.3, "b": -0.05}

    destination = drawingml_fill_destination(200.0, 100.0, fill_rect)
    assert destination.x == pytest.approx(-50.0)
    assert destination.y == pytest.approx(-10.0)
    assert destination.width == pytest.approx(310.0)
    assert destination.height == pytest.approx(115.0)


def test_existing_picture_fill_image_receives_clip_path_during_fidelity_pass() -> None:
    root, _shape = _picture_fill_custom_shape()
    page = GraphicsPage(width=1080.0, height=1350.0)
    image = _image_node()
    page.add_node(image)
    report = PptxFidelityReport()

    _enrich_page(page, root, 10_287_000, 12_852_400, report)

    assert report.image_clips_enriched == 1
    assert image.metadata.get("clip_path") is not None
    commands = image.metadata["clip_path"]["paths"][0]["commands"]
    assert [command["op"] for command in commands] == ["M", "L", "L", "Z"]


def test_custgeom_loss_point_is_late_image_recovery_after_fidelity_pass() -> None:
    """Pin the current pass-order gap without introducing a visual workaround.

    ``enhance_pptx_document`` can only attach custGeom to IMAGE nodes that exist
    at fidelity-pass time.  ``recover_pptx_fill_rects`` subsequently invokes
    artwork recovery, which may create an IMAGE node.  There is currently no
    second custGeom enrichment pass after that recovery, so a late image keeps
    its fillRect semantics but lacks the non-rectangular clip_path.
    """

    root, _shape = _picture_fill_custom_shape()
    page = GraphicsPage(width=1080.0, height=1350.0)
    report = PptxFidelityReport()

    _enrich_page(page, root, 10_287_000, 12_852_400, report)
    assert report.image_clips_enriched == 0

    late_image = _image_node()
    late_image.style["fill_rect"] = {"l": -0.25, "t": -0.1, "r": -0.3, "b": -0.05}
    page.add_node(late_image)

    assert late_image.style["fill_rect"]["l"] < 0
    assert "clip_path" not in late_image.metadata
