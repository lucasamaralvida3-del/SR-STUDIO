from __future__ import annotations

import base64
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

import pytest

from srstudio.core.models import Page
from srstudio.graphics2.image_fill import drawingml_fill_destination
from srstudio.graphics2.import_bridge import GraphicsImportService
from srstudio.graphics2.model import GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.pptx_fidelity import PptxFidelityReport, _custom_path_spec, _enrich_page
from srstudio.graphics2.pptx_fill_rect import _rect_percent
from srstudio.importers.pipeline import ImportSummary


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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


def _write_late_artwork_pptx(path: Path) -> Path:
    presentation = (
        f'<p:presentation xmlns:p="{P_NS}">'
        '<p:sldSz cx="1000000" cy="1000000"/>'
        '</p:presentation>'
    )
    slide = f'''<p:sld xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}">
 <p:cSld><p:spTree><p:nvGrpSpPr/><p:grpSpPr/>
 <p:sp><p:nvSpPr><p:cNvPr id="7" name="Masked Photo"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
 <p:spPr>
  <a:xfrm><a:off x="100000" y="200000"/><a:ext cx="400000" cy="300000"/></a:xfrm>
  <a:custGeom><a:pathLst><a:path w="100000" h="100000">
   <a:moveTo><a:pt x="0" y="0"/></a:moveTo>
   <a:lnTo><a:pt x="100000" y="0"/></a:lnTo>
   <a:lnTo><a:pt x="50000" y="100000"/></a:lnTo><a:close/>
  </a:path></a:pathLst></a:custGeom>
  <a:blipFill><a:blip r:embed="rId1"/><a:stretch>
   <a:fillRect l="-25000" t="-10000" r="-30000" b="-5000"/>
  </a:stretch></a:blipFill>
 </p:spPr></p:sp></p:spTree></p:cSld></p:sld>'''
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Target="../media/image1.png" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        archive.writestr("ppt/media/image1.png", PNG)
    return path


class _NoImagePipeline:
    def import_file(self, path, project):
        project.pages = [Page(width=1080, height=1350, elements=[])]
        return ImportSummary(str(path))


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


def test_import_bridge_recovers_late_artwork_before_custgeom_fidelity_pass(tmp_path) -> None:
    source = _write_late_artwork_pptx(tmp_path / "late-artwork-custgeom.pptx")
    service = GraphicsImportService()
    service.pipeline = _NoImagePipeline()

    result = service.import_file(source, project_name="custGeom order regression")
    images = [node for node in result.document.active_page.nodes.values() if node.kind is NodeKind.IMAGE]

    assert len(images) == 1
    image = images[0]
    assert image.metadata.get("pptx_artwork_recovered") is True
    assert image.metadata.get("clip_path") is not None
    assert [command["op"] for command in image.metadata["clip_path"]["paths"][0]["commands"]] == ["M", "L", "L", "Z"]
    assert image.style["fill_rect"] == pytest.approx({"l": -0.25, "t": -0.1, "r": -0.3, "b": -0.05})
    assert result.document.metadata["pptx_artwork_recovery"]["recovered_nodes"] == 1
    assert result.document.metadata["pptx_fill_rect_recovery"]["coverage"] == pytest.approx(1.0)
