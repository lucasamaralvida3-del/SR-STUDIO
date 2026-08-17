from __future__ import annotations

from zipfile import ZipFile

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_image_transform_runtime import recover_pptx_image_transforms_professional


PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="1000" cy="1000"/>
</p:presentation>
"""

SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="4" name="Imagem 3"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId4"/></p:blipFill>
      <p:spPr><a:xfrm><a:off x="100" y="100"/><a:ext cx="100" cy="100"/></a:xfrm></p:spPr>
    </p:pic>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="22" name="Imagem 3"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId22"/></p:blipFill>
      <p:spPr><a:xfrm flipV="1"><a:off x="700" y="700"/><a:ext cx="100" cy="100"/></a:xfrm></p:spPr>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/slides/slide1.xml", SLIDE)
    return path


def _node(node_id: str, *, shape_id: str = "") -> GraphicsNode:
    metadata = {"source": "pptx", "source_name": "Imagem 3"}
    if shape_id:
        metadata["pptx_shape_id"] = shape_id
    return GraphicsNode(
        id=node_id,
        kind=NodeKind.IMAGE,
        name="Imagem 3",
        transform=Transform(x=350, y=350, width=100, height=100),
        style={"flip_x": False, "flip_y": False},
        metadata=metadata,
    )


def test_known_shape_id_eliminates_only_other_duplicate_candidate(tmp_path):
    document = GraphicsDocument(name="one-to-one image identity")
    page = document.active_page
    page.width = 1000
    page.height = 1000
    unknown = _node("unknown")
    known = _node("known-22", shape_id="22")
    page.add_node(unknown)
    page.add_node(known)

    report = recover_pptx_image_transforms_professional(_pptx(tmp_path / "identity.pptx"), document)

    assert report.source_contracts == 2
    assert report.mapped_contracts == 2
    assert report.exact_contracts == 2
    assert report.exact_non_identity_contracts == 1
    assert report.coverage == 1.0
    assert not report.issues
    assert unknown.metadata["pptx_shape_id"] == "4"
    assert unknown.metadata["pptx_image_transform_match"] == "shape-id-elimination"
    assert known.metadata["pptx_shape_id"] == "22"
    assert known.style["flip_y"] is True


def test_elimination_stays_ambiguous_when_two_unidentified_candidates_remain(tmp_path):
    document = GraphicsDocument(name="still ambiguous")
    page = document.active_page
    page.width = 1000
    page.height = 1000
    page.add_node(_node("unknown-a"))
    page.add_node(_node("unknown-b"))

    report = recover_pptx_image_transforms_professional(_pptx(tmp_path / "ambiguous.pptx"), document)

    assert report.exact_contracts == 0
    assert any(issue.code == "PPTX_IMAGE_TRANSFORM_SHAPE_AMBIGUOUS" for issue in report.issues)
