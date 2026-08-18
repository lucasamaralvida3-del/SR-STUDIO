from __future__ import annotations

from dataclasses import asdict
from zipfile import ZipFile

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_group_transform import recover_pptx_group_member_transforms
from srstudio.graphics2.pptx_groups import rebuild_pptx_groups


PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="100" cy="100"/>
</p:presentation>
"""


def _shape(name: str, *, text: bool = True, rot: int = 0) -> str:
    tx_body = ""
    if text:
        tx_body = f"<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{name}</a:t></a:r></a:p></p:txBody>"
    return f"""
<p:sp>
  <p:nvSpPr><p:cNvPr id="7" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm rot="{rot}"><a:off x="0" y="0"/><a:ext cx="50" cy="50"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
  {tx_body}
</p:sp>
"""


def _slide(group_xfrm: str, shape_xml: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:grpSp>
      <p:nvGrpSpPr><p:cNvPr id="5" name="Grupo"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr>{group_xfrm}</p:grpSpPr>
      {shape_xml}
    </p:grpSp>
  </p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path, xml: str):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/slides/slide1.xml", xml)
    return path


def _node(kind: NodeKind, name: str, *, rotation=0.0) -> GraphicsNode:
    return GraphicsNode(
        id=name.casefold().replace(" ", "-"),
        kind=kind,
        name=name,
        text=name if kind is NodeKind.TEXT else "",
        transform=Transform(x=50, y=0, width=50, height=50, rotation=rotation),
        metadata={"source": "pptx", "source_name": name, "grouped": True, "group_depth": 1, "group_name": "Grupo"},
    )


def test_rotated_group_restores_text_orientation_without_renderer(tmp_path):
    group = '<a:xfrm rot="5400000"><a:off x="0" y="0"/><a:ext cx="100" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm>'
    source = _pptx(tmp_path / "rotated-text.pptx", _slide(group, _shape("Grouped Text")))
    document = GraphicsDocument(name="rotated text")
    document.active_page.width = document.active_page.height = 100
    node = _node(NodeKind.TEXT, "Grouped Text")
    document.active_page.add_node(node)

    report = recover_pptx_group_member_transforms(source, document)

    assert report.source_members == 1
    assert report.mapped_members == 1
    assert report.exact_members == 1
    assert report.corrected_members == 1
    assert report.deferred_shear_members == 0
    assert report.coverage == 1.0
    assert node.transform.x == 50.0
    assert node.transform.y == 0.0
    assert node.transform.width == 50.0
    assert node.transform.height == 50.0
    assert node.transform.rotation == 90.0
    assert node.transform.scale_x == 1.0
    assert node.transform.scale_y == 1.0
    assert node.metadata["pptx_group_member_transform_previous"]["rotation"] == 0.0


def test_group_flip_is_decomposed_into_scene_rotation_and_reflection(tmp_path):
    group = '<a:xfrm flipH="1"><a:off x="0" y="0"/><a:ext cx="100" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm>'
    source = _pptx(tmp_path / "flipped-shape.pptx", _slide(group, _shape("Grouped Shape", text=False)))
    document = GraphicsDocument(name="flipped shape")
    document.active_page.width = document.active_page.height = 100
    node = _node(NodeKind.RECT, "Grouped Shape")
    document.active_page.add_node(node)

    report = recover_pptx_group_member_transforms(source, document)

    assert report.exact_members == 1
    assert node.transform.rotation == 180.0
    assert node.transform.scale_x == 1.0
    assert node.transform.scale_y == -1.0
    assert node.metadata["pptx_group_member_transform"] == {
        "rotation": 180.0,
        "flip_x": False,
        "flip_y": True,
        "group_composed": True,
    }


def test_anisotropic_group_plus_rotated_text_defers_shear_without_mutation(tmp_path):
    group = '<a:xfrm><a:off x="0" y="0"/><a:ext cx="200" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm>'
    source = _pptx(tmp_path / "sheared-text.pptx", _slide(group, _shape("Sheared Text", rot=2700000)))
    document = GraphicsDocument(name="sheared text")
    document.active_page.width = document.active_page.height = 100
    node = _node(NodeKind.TEXT, "Sheared Text", rotation=45.0)
    before = asdict(node.transform)
    document.active_page.add_node(node)

    report = recover_pptx_group_member_transforms(source, document)

    assert report.source_members == 1
    assert report.mapped_members == 1
    assert report.exact_members == 0
    assert report.corrected_members == 0
    assert report.deferred_shear_members == 1
    assert report.coverage == 0.0
    assert asdict(node.transform) == before
    assert any(issue.code == "PPTX_GROUP_MEMBER_SHEAR_DEFERRED" for issue in report.issues)


def test_group_rebuild_runs_transform_recovery_before_reparenting(tmp_path):
    group = '<a:xfrm rot="5400000"><a:off x="0" y="0"/><a:ext cx="100" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm>'
    source = _pptx(tmp_path / "group-pipeline.pptx", _slide(group, _shape("Pipeline Text")))
    document = GraphicsDocument(name="group pipeline")
    document.active_page.width = document.active_page.height = 100
    node = _node(NodeKind.TEXT, "Pipeline Text")
    document.active_page.add_node(node)

    group_report = rebuild_pptx_groups(source, document)
    recovery = document.metadata["pptx_group_member_transform_recovery"]
    rebuilt = next(item for item in document.active_page.nodes.values() if item.kind is NodeKind.GROUP)

    assert recovery["source_members"] == 1
    assert recovery["exact_members"] == 1
    assert recovery["coverage"] == 1.0
    assert node.transform.rotation == 90.0
    assert node.parent_id == rebuilt.id
    assert group_report.groups_rebuilt == 1
    assert group_report.nodes_reparented == 1
