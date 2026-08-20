from __future__ import annotations

from dataclasses import asdict
from zipfile import ZipFile

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_groups import rebuild_pptx_groups
from srstudio.graphics2.pptx_shape_visual import recover_pptx_shape_visuals


PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="100" cy="100"/>
</p:presentation>
"""


def _shape(
    name: str,
    *,
    geometry: str = "rect",
    with_text: bool = True,
    fill_alpha: int = 50000,
    text_alpha: int = 75000,
) -> str:
    text = ""
    if with_text:
        text = f"""
<p:txBody>
  <a:bodyPr/><a:lstStyle/>
  <a:p><a:r><a:rPr><a:solidFill><a:srgbClr val="000000"><a:alpha val="{text_alpha}"/></a:srgbClr></a:solidFill></a:rPr><a:t>{name}</a:t></a:r></a:p>
</p:txBody>
"""
    return f"""
<p:sp>
  <p:nvSpPr><p:cNvPr id="7" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="10" y="20"/><a:ext cx="30" cy="40"/></a:xfrm>
    <a:prstGeom prst="{geometry}"><a:avLst/></a:prstGeom>
    <a:solidFill><a:srgbClr val="336699"><a:alpha val="{fill_alpha}"/></a:srgbClr></a:solidFill>
    <a:ln w="2"><a:solidFill><a:srgbClr val="FF0000"><a:alpha val="25000"/></a:srgbClr></a:solidFill></a:ln>
  </p:spPr>
  {text}
</p:sp>
"""


def _compound_shape(name: str = "Compound") -> str:
    return f"""
<p:sp>
  <p:nvSpPr><p:cNvPr id="9" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="10" y="20"/><a:ext cx="30" cy="40"/></a:xfrm>
    <a:blipFill><a:blip r:embed="rId9"/></a:blipFill>
  </p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr><a:solidFill><a:srgbClr val="112233"><a:alpha val="50000"/></a:srgbClr></a:solidFill></a:rPr><a:t>{name}</a:t></a:r></a:p></p:txBody>
</p:sp>
"""


def _slide(body: str, *, grouped: bool = False) -> str:
    if grouped:
        body = f"""
<p:grpSp>
  <p:nvGrpSpPr><p:cNvPr id="5" name="Grupo"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
  <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm></p:grpSpPr>
  {body}
</p:grpSp>
"""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>{body}</p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path, body: str, *, grouped: bool = False):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/slides/slide1.xml", _slide(body, grouped=grouped))
    return path


def _text(name: str, *, z=4, grouped=False) -> GraphicsNode:
    return GraphicsNode(
        id=f"text-{name}",
        kind=NodeKind.TEXT,
        name=name,
        text=name,
        transform=Transform(x=10, y=20, width=30, height=40),
        z_index=z,
        style={"color": "#000000", "fill": "#000000"},
        metadata={
            "source": "pptx",
            "source_name": name,
            "grouped": grouped,
            "group_depth": 1 if grouped else 0,
            "group_name": "Grupo" if grouped else "",
        },
    )


def _after() -> GraphicsNode:
    return GraphicsNode(
        id="after",
        kind=NodeKind.RECT,
        name="Depois",
        transform=Transform(x=80, y=80, width=10, height=10),
        z_index=5,
    )


def _visual(document: GraphicsDocument) -> GraphicsNode:
    return next(
        node
        for node in document.active_page.nodes.values()
        if node.metadata.get("pptx_text_shape_visual_recovered")
    )


def test_recovers_rect_fill_outline_text_alpha_geometry_and_z_order(tmp_path):
    source = _pptx(tmp_path / "text-shape.pptx", _shape("Label"))
    document = GraphicsDocument(name="text shape")
    page = document.active_page
    page.width = page.height = 100
    owner = _text("Label")
    after = _after()
    page.add_node(owner)
    page.add_node(after)

    report = recover_pptx_shape_visuals(source, document)
    visual = _visual(document)

    assert report.text_shapes == 1
    assert report.text_colors_corrected == 1
    assert report.visual_shapes == 1
    assert report.visuals_recovered == 1
    assert report.existing_visuals == 0
    assert report.deferred_geometry == 0
    assert report.visual_coverage == 1.0
    assert owner.style["color"] == "#BF000000"
    assert owner.style["fill"] == "#BF000000"
    assert visual.kind is NodeKind.RECT
    assert visual.style["fill"] == "#80336699"
    assert visual.style["stroke"] == "#40FF0000"
    assert visual.style["outline"] == "#40FF0000"
    assert visual.style["stroke_width"] == 2.0
    assert asdict(visual.transform) == asdict(owner.transform)
    assert visual.z_index == 4
    assert owner.z_index == 5
    assert after.z_index == 6
    assert visual.metadata["pptx_compound_owner_id"] == owner.id


def test_text_shape_visual_recovery_is_idempotent(tmp_path):
    source = _pptx(tmp_path / "idempotent.pptx", _shape("Label"))
    document = GraphicsDocument(name="idempotent")
    document.active_page.width = document.active_page.height = 100
    owner = _text("Label")
    document.active_page.add_node(owner)

    first = recover_pptx_shape_visuals(source, document)
    first_z = owner.z_index
    second = recover_pptx_shape_visuals(source, document)
    visuals = [node for node in document.active_page.nodes.values() if node.metadata.get("pptx_text_shape_visual_recovered")]

    assert first.visuals_recovered == 1
    assert second.visuals_recovered == 0
    assert second.existing_visuals == 1
    assert second.visual_coverage == 1.0
    assert len(visuals) == 1
    assert owner.z_index == first_z


def test_round_rect_is_deferred_instead_of_approximated_as_plain_rect(tmp_path):
    source = _pptx(tmp_path / "round-rect.pptx", _shape("Rounded", geometry="roundRect"))
    document = GraphicsDocument(name="round rect")
    document.active_page.width = document.active_page.height = 100
    document.active_page.add_node(_text("Rounded"))

    report = recover_pptx_shape_visuals(source, document)

    assert report.visual_shapes == 1
    assert report.visuals_recovered == 0
    assert report.deferred_geometry == 1
    assert report.visual_coverage == 0.0
    assert not any(node.metadata.get("pptx_text_shape_visual_recovered") for node in document.active_page.nodes.values())
    assert any(issue.code == "PPTX_TEXT_SHAPE_GEOMETRY_DEFERRED" for issue in report.issues)


def test_corrects_alpha_on_existing_pure_vector_shape_without_overlay(tmp_path):
    source = _pptx(tmp_path / "pure-shape.pptx", _shape("Pure", with_text=False))
    document = GraphicsDocument(name="pure shape")
    document.active_page.width = document.active_page.height = 100
    node = GraphicsNode(
        id="pure",
        kind=NodeKind.RECT,
        name="Pure",
        transform=Transform(x=10, y=20, width=30, height=40),
        style={"fill": "#336699", "stroke": "#FF0000"},
        metadata={"source": "pptx", "source_name": "Pure"},
    )
    document.active_page.add_node(node)

    report = recover_pptx_shape_visuals(source, document)

    assert report.pure_shape_colors_corrected == 1
    assert node.style["fill"] == "#80336699"
    assert node.style["stroke"] == "#40FF0000"
    assert node.style["outline"] == "#40FF0000"
    assert node.style["stroke_width"] == 2.0
    assert node.metadata["pptx_shape_alpha_recovered"] is True


def test_corrects_text_alpha_on_existing_picture_fill_compound_overlay(tmp_path):
    source = _pptx(tmp_path / "compound-alpha.pptx", _compound_shape())
    document = GraphicsDocument(name="compound alpha")
    document.active_page.width = document.active_page.height = 100
    overlay = GraphicsNode(
        id="compound-text",
        kind=NodeKind.TEXT,
        name="Compound",
        text="Compound",
        transform=Transform(x=10, y=20, width=30, height=40),
        style={"color": "#112233", "fill": "#112233"},
        metadata={
            "source": "pptx-compound-text",
            "source_name": "Compound",
            "pptx_compound_text_recovered": True,
            "pptx_compound_owner_id": "image-owner",
        },
    )
    document.active_page.add_node(overlay)

    report = recover_pptx_shape_visuals(source, document)

    assert report.compound_text_colors_corrected == 1
    assert overlay.style["color"] == "#80112233"
    assert overlay.style["fill"] == "#80112233"


def test_group_rebuild_reparents_text_and_visual_companion_together(tmp_path):
    source = _pptx(tmp_path / "grouped-text-shape.pptx", _shape("Grouped Label"), grouped=True)
    document = GraphicsDocument(name="grouped text shape")
    page = document.active_page
    page.width = page.height = 100
    owner = _text("Grouped Label", grouped=True)
    page.add_node(owner)

    groups = rebuild_pptx_groups(source, document)
    visual = _visual(document)
    group = next(node for node in page.nodes.values() if node.kind is NodeKind.GROUP)
    recovery = document.metadata["pptx_shape_visual_recovery"]

    assert recovery["visuals_recovered"] == 1
    assert recovery["visual_coverage"] == 1.0
    assert groups.groups_rebuilt == 1
    assert groups.nodes_reparented == 2
    assert owner.parent_id == group.id
    assert visual.parent_id == group.id
    assert owner.id in group.children
    assert visual.id in group.children
