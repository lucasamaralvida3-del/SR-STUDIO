from __future__ import annotations

from zipfile import ZipFile

import pytest

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_fill_rect import recover_pptx_fill_rects


SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="7" name="Freeform 7"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:blipFill><a:blip r:embed="rId7"/><a:stretch><a:fillRect l="-30959" t="0" r="-30437" b="-30482"/></a:stretch></a:blipFill>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
      </p:spPr>
    </p:sp>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="9" name="Picture 9"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId9"/><a:stretch><a:fillRect l="0" t="0" r="0" b="0"/></a:stretch></p:blipFill>
      <p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", SLIDE)
    return path


def _image(node_id: str, name: str, fill_rect=None):
    return GraphicsNode(
        id=node_id,
        kind=NodeKind.IMAGE,
        name=name,
        transform=Transform(width=200, height=120),
        style={"fill_rect": dict(fill_rect or {})},
        metadata={"source": "pptx", "source_name": name},
    )


def test_recovers_exact_shape_and_picture_fill_rect_contracts(tmp_path):
    document = GraphicsDocument(name="fillRect exact")
    page = document.active_page
    page.add_node(_image("shape", "Freeform 7", {"l": -0.2, "t": 0, "r": -0.2, "b": 0}))
    page.add_node(_image("picture", "Picture 9", {"l": 0, "t": 0, "r": 0, "b": 0}))

    report = recover_pptx_fill_rects(_pptx(tmp_path / "fills.pptx"), document)
    shape = page.node("shape")
    picture = page.node("picture")

    assert report.source_contracts == 2
    assert report.mapped_contracts == 2
    assert report.exact_contracts == 2
    assert report.corrected_contracts == 1
    assert report.source_outsets == 1
    assert report.exact_outsets == 1
    assert report.coverage == 1.0
    assert report.outset_coverage == 1.0
    assert shape.style["fill_rect"] == pytest.approx({"l": -0.30959, "t": 0.0, "r": -0.30437, "b": -0.30482})
    assert shape.metadata["pptx_fill_rect_previous"] == pytest.approx({"l": -0.2, "t": 0.0, "r": -0.2, "b": 0.0})
    assert picture.style["fill_rect"] == pytest.approx({"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0})
    assert shape.metadata["pptx_shape_id"] == "7"
    assert picture.metadata["pptx_shape_id"] == "9"


def test_explicit_zero_fill_rect_is_preserved_as_a_real_contract(tmp_path):
    document = GraphicsDocument(name="fillRect zero")
    document.active_page.add_node(_image("shape", "Freeform 7", {"l": -0.30959, "t": 0, "r": -0.30437, "b": -0.30482}))
    document.active_page.add_node(_image("picture", "Picture 9"))

    report = recover_pptx_fill_rects(_pptx(tmp_path / "zero.pptx"), document)
    picture = document.active_page.node("picture")

    assert report.corrected_contracts == 1
    assert picture.style["fill_rect"] == {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}
    assert report.coverage == 1.0


def test_does_not_guess_duplicate_image_shape_names(tmp_path):
    document = GraphicsDocument(name="fillRect ambiguity")
    page = document.active_page
    page.add_node(_image("a", "Freeform 7"))
    page.add_node(_image("b", "Freeform 7"))
    page.add_node(_image("picture", "Picture 9"))

    report = recover_pptx_fill_rects(_pptx(tmp_path / "ambiguous.pptx"), document)

    assert report.source_contracts == 2
    assert report.mapped_contracts == 1
    assert report.exact_contracts == 1
    assert report.coverage == 0.5
    assert any(issue.code == "PPTX_FILL_RECT_SHAPE_AMBIGUOUS" for issue in report.issues)
    assert page.node("a").style["fill_rect"] == {}
    assert page.node("b").style["fill_rect"] == {}
