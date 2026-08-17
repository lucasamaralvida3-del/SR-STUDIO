from __future__ import annotations

from zipfile import ZipFile

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_image_transform import recover_pptx_image_transforms


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
    <p:sp>
      <p:nvSpPr><p:cNvPr id="3" name="Freeform 3"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:xfrm rot="-10800000"><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm>
        <a:blipFill><a:blip r:embed="rId3"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>
      </p:spPr>
    </p:sp>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="4" name="Picture 4"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId4"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
      <p:spPr><a:xfrm flipH="1" flipV="1"><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm></p:spPr>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>
"""

GROUPED = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:grpSp>
      <p:nvGrpSpPr><p:cNvPr id="20" name="Rotated Group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm rot="5400000"><a:off x="0" y="0"/><a:ext cx="100" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm></p:grpSpPr>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="21" name="Grouped Image"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="50" cy="50"/></a:xfrm><a:blipFill><a:blip r:embed="rId21"/></a:blipFill></p:spPr>
      </p:sp>
    </p:grpSp>
  </p:spTree></p:cSld>
</p:sld>
"""

DUPLICATE_NAMES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="4" name="Imagem 3"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId4"/></p:blipFill>
      <p:spPr><a:xfrm><a:off x="100" y="200"/><a:ext cx="120" cy="160"/></a:xfrm></p:spPr>
    </p:pic>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="22" name="Imagem 3"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId22"/></p:blipFill>
      <p:spPr><a:xfrm flipH="1"><a:off x="700" y="220"/><a:ext cx="140" cy="150"/></a:xfrm></p:spPr>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path, xml=SLIDE):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/slides/slide1.xml", xml)
    return path


def _image(
    node_id: str,
    name: str,
    *,
    x=0.0,
    y=0.0,
    width=100.0,
    height=100.0,
    rotation=0.0,
    flip_x=False,
    flip_y=False,
):
    return GraphicsNode(
        id=node_id,
        kind=NodeKind.IMAGE,
        name=name,
        transform=Transform(x=x, y=y, width=width, height=height, rotation=rotation),
        style={"flip_x": flip_x, "flip_y": flip_y},
        metadata={"source": "pptx", "source_name": name},
    )


def test_recovers_minus_180_rotation_and_picture_flips_exactly(tmp_path):
    document = GraphicsDocument(name="image transform")
    page = document.active_page
    page.add_node(_image("freeform3", "Freeform 3", rotation=0.0))
    page.add_node(_image("picture4", "Picture 4", flip_x=False, flip_y=False))

    report = recover_pptx_image_transforms(_pptx(tmp_path / "transform.pptx"), document)
    freeform = page.node("freeform3")
    picture = page.node("picture4")

    assert report.source_contracts == 2
    assert report.non_identity_contracts == 2
    assert report.mapped_contracts == 2
    assert report.exact_contracts == 2
    assert report.exact_non_identity_contracts == 2
    assert report.corrected_contracts == 2
    assert report.coverage == 1.0
    assert report.non_identity_coverage == 1.0
    assert freeform.transform.rotation == -180.0
    assert freeform.style["flip_x"] is False
    assert freeform.style["flip_y"] is False
    assert picture.transform.rotation == 0.0
    assert picture.style["flip_x"] is True
    assert picture.style["flip_y"] is True
    assert freeform.metadata["pptx_image_transform_previous"]["rotation"] == 0.0


def test_equivalent_rotation_modulo_360_is_not_reported_as_correction(tmp_path):
    document = GraphicsDocument(name="rotation equivalence")
    document.active_page.add_node(_image("freeform3", "Freeform 3", rotation=180.0))
    document.active_page.add_node(_image("picture4", "Picture 4", flip_x=True, flip_y=True))

    report = recover_pptx_image_transforms(_pptx(tmp_path / "equivalent.pptx"), document)

    assert report.corrected_contracts == 0
    assert report.exact_contracts == 2
    # A SR Scene passa a guardar o valor fonte, embora 180 e -180 sejam
    # visualmente equivalentes e portanto não contem como correção.
    assert document.active_page.node("freeform3").transform.rotation == -180.0


def test_transformed_group_is_deferred_instead_of_falsely_marked_exact(tmp_path):
    document = GraphicsDocument(name="group transform")
    document.active_page.add_node(_image("grouped", "Grouped Image"))

    report = recover_pptx_image_transforms(_pptx(tmp_path / "grouped.pptx", GROUPED), document)

    assert report.source_contracts == 1
    assert report.mapped_contracts == 1
    assert report.exact_contracts == 0
    assert report.deferred_group_contracts == 1
    assert report.coverage == 0.0
    assert any(issue.code == "PPTX_IMAGE_TRANSFORM_GROUP_COMPOSITION_DEFERRED" for issue in report.issues)
    assert document.active_page.node("grouped").transform.rotation == 0.0


def test_duplicate_image_names_are_resolved_by_slide_geometry_without_guessing(tmp_path):
    document = GraphicsDocument(name="duplicate image names")
    page = document.active_page
    page.width = 1000
    page.height = 1000
    left = _image("left", "Imagem 3", x=100, y=200, width=120, height=160)
    right = _image("right", "Imagem 3", x=700, y=220, width=140, height=150)
    page.add_node(left)
    page.add_node(right)

    report = recover_pptx_image_transforms(
        _pptx(tmp_path / "duplicate-names.pptx", DUPLICATE_NAMES),
        document,
    )

    assert report.source_contracts == 2
    assert report.mapped_contracts == 2
    assert report.exact_contracts == 2
    assert report.geometry_matches == 2
    assert report.coverage == 1.0
    assert not report.issues
    assert left.metadata["pptx_shape_id"] == "4"
    assert right.metadata["pptx_shape_id"] == "22"
    assert left.metadata["pptx_image_transform_match"] == "geometry"
    assert right.metadata["pptx_image_transform_match"] == "geometry"
    assert left.style["flip_x"] is False
    assert right.style["flip_x"] is True
