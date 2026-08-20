from __future__ import annotations

from zipfile import ZipFile

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_compound_text import recover_pptx_compound_text
from srstudio.graphics2.pptx_fill_rect import recover_pptx_fill_rects
from srstudio.graphics2.pptx_groups import rebuild_pptx_groups
from srstudio.graphics2.pptx_text_content import recover_pptx_text_content


PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="100" cy="100"/>
</p:presentation>
"""

SHAPE = """
<p:sp>
  <p:nvSpPr><p:cNvPr id="7" name="Card"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm rot="900000"><a:off x="10" y="20"/><a:ext cx="30" cy="40"/></a:xfrm>
    <a:blipFill><a:blip r:embed="rId7"/><a:stretch><a:fillRect l="-1000"/></a:stretch></a:blipFill>
  </p:spPr>
  <p:txBody>
    <a:bodyPr anchor="b" lIns="10" tIns="20" rIns="30" bIns="40"><a:normAutofit/></a:bodyPr>
    <a:lstStyle/>
    <a:p>
      <a:pPr algn="ctr"><a:lnSpc><a:spcPct val="120000"/></a:lnSpc></a:pPr>
      <a:r>
        <a:rPr sz="1800" b="1" spc="100"><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill><a:latin typeface="Aptos"/></a:rPr>
        <a:t xml:space="preserve"> PREÇO </a:t>
      </a:r>
    </a:p>
    <a:p/>
  </p:txBody>
</p:sp>
"""


def _slide(*, grouped: bool = False) -> str:
    body = SHAPE
    if grouped:
        body = f"""
<p:grpSp>
  <p:nvGrpSpPr><p:cNvPr id="5" name="Grupo Card"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
  <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm></p:grpSpPr>
  {SHAPE}
</p:grpSp>
"""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>{body}</p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path, *, grouped: bool = False):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/slides/slide1.xml", _slide(grouped=grouped))
    return path


def _document(*, grouped: bool = False) -> tuple[GraphicsDocument, GraphicsNode, GraphicsNode]:
    document = GraphicsDocument(name="compound")
    page = document.active_page
    page.width = 100
    page.height = 100
    image = GraphicsNode(
        id="image-card",
        kind=NodeKind.IMAGE,
        name="Card",
        transform=Transform(x=10, y=20, width=30, height=40, rotation=15),
        z_index=4,
        metadata={
            "source": "pptx",
            "source_name": "Card",
            "grouped": grouped,
            "group_depth": 1 if grouped else 0,
            "group_name": "Grupo Card" if grouped else "",
        },
    )
    after = GraphicsNode(
        id="after",
        kind=NodeKind.RECT,
        name="Depois",
        transform=Transform(x=80, y=80, width=10, height=10),
        z_index=5,
    )
    page.add_node(image)
    page.add_node(after)
    return document, image, after


def _overlay(document: GraphicsDocument) -> GraphicsNode:
    return next(
        node
        for node in document.active_page.nodes.values()
        if node.kind is NodeKind.TEXT and node.metadata.get("pptx_compound_text_recovered")
    )


def test_recovers_text_style_geometry_and_z_order_from_picture_filled_shape(tmp_path):
    source = _pptx(tmp_path / "compound.pptx")
    document, image, after = _document()

    report = recover_pptx_compound_text(source, document)
    overlay = _overlay(document)

    assert report.source_shapes == 1
    assert report.matched_images == 1
    assert report.recovered_text_nodes == 1
    assert report.existing_text_nodes == 0
    assert report.coverage == 1.0
    assert overlay.text == " PREÇO \n"
    assert overlay.transform.x == image.transform.x
    assert overlay.transform.y == image.transform.y
    assert overlay.transform.width == image.transform.width
    assert overlay.transform.height == image.transform.height
    assert overlay.transform.rotation == image.transform.rotation
    assert overlay.z_index == 5
    assert after.z_index == 6
    assert overlay.metadata["pptx_compound_owner_id"] == image.id
    assert overlay.style["font_family"] == "Aptos"
    assert overlay.style["font_size"] == 18.0
    assert overlay.style["bold"] is True
    assert overlay.style["fill"] == "#FF0000"
    assert overlay.style["align"] == "center"
    assert overlay.style["v_align"] == "bottom"
    assert overlay.style["fit_inside_box"] is True
    assert overlay.style["pptx_auto_fit"] == "normal"
    assert overlay.style["letter_spacing_pt"] == 1.0
    assert overlay.style["line_spacing_percent"] == 120.0
    assert overlay.style["text_insets"] == {"left": 10.0, "top": 20.0, "right": 30.0, "bottom": 40.0}


def test_compound_text_recovery_is_idempotent(tmp_path):
    source = _pptx(tmp_path / "idempotent.pptx")
    document, _, _ = _document()

    first = recover_pptx_compound_text(source, document)
    second = recover_pptx_compound_text(source, document)
    overlays = [node for node in document.active_page.nodes.values() if node.kind is NodeKind.TEXT]

    assert first.recovered_text_nodes == 1
    assert second.recovered_text_nodes == 0
    assert second.existing_text_nodes == 1
    assert second.coverage == 1.0
    assert len(overlays) == 1


def test_common_text_contract_excludes_picture_filled_shape_to_avoid_false_missing(tmp_path):
    source = _pptx(tmp_path / "separate-contracts.pptx")
    document, _, _ = _document()

    report = recover_pptx_text_content(source, document)

    assert report.source_contracts == 0
    assert report.coverage == 1.0
    assert report.issues == []


def test_fill_rect_pipeline_restores_compound_text_after_image_transform(tmp_path):
    source = _pptx(tmp_path / "pipeline.pptx")
    document, image, _ = _document()
    image.transform.rotation = 0

    fill_report = recover_pptx_fill_rects(source, document)
    overlay = _overlay(document)
    compound = document.metadata["pptx_compound_text_recovery"]

    assert fill_report.source_contracts == 1
    assert fill_report.exact_contracts == 1
    assert image.transform.rotation == 15.0
    assert overlay.transform.rotation == 15.0
    assert overlay.transform.x == image.transform.x
    assert overlay.transform.y == image.transform.y
    assert compound["source_shapes"] == 1
    assert compound["recovered_text_nodes"] == 1
    assert compound["coverage"] == 1.0


def test_group_rebuild_reparents_picture_and_recovered_text_together(tmp_path):
    source = _pptx(tmp_path / "grouped-compound.pptx", grouped=True)
    document, image, _ = _document(grouped=True)

    compound = recover_pptx_compound_text(source, document)
    overlay = _overlay(document)
    groups = rebuild_pptx_groups(source, document)
    group = next(node for node in document.active_page.nodes.values() if node.kind is NodeKind.GROUP)

    assert compound.recovered_text_nodes == 1
    assert groups.groups_rebuilt == 1
    assert groups.nodes_reparented == 2
    assert image.parent_id == group.id
    assert overlay.parent_id == group.id
    assert image.id in group.children
    assert overlay.id in group.children
