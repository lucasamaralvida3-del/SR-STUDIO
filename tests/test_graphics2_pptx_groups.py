from __future__ import annotations

from pathlib import Path
import zipfile

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_groups import rebuild_pptx_groups
from srstudio.graphics2.preflight import run_preflight


SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:cSld><p:spTree>
   <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
   <p:grpSpPr/>
   <p:grpSp>
     <p:nvGrpSpPr><p:cNvPr id="10" name="Grupo Produto 1"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
     <p:grpSpPr/>
     <p:sp>
       <p:nvSpPr><p:cNvPr id="11" name="Nome Produto"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
       <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>ACÉM</a:t></a:r></a:p></p:txBody>
     </p:sp>
     <p:grpSp>
       <p:nvGrpSpPr><p:cNvPr id="12" name="Grupo Preço"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
       <p:grpSpPr/>
       <p:sp>
         <p:nvSpPr><p:cNvPr id="13" name="Preço Inteiro"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
         <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>29</a:t></a:r></a:p></p:txBody>
       </p:sp>
       <p:sp>
         <p:nvSpPr><p:cNvPr id="14" name="Preço Centavos"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
         <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>99</a:t></a:r></a:p></p:txBody>
       </p:sp>
     </p:grpSp>
   </p:grpSp>
 </p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", SLIDE)
    return path


def _document() -> GraphicsDocument:
    document = GraphicsDocument(name="Groups")
    page = document.active_page
    for index, (name, x, y, width, height) in enumerate(
        [
            ("Nome Produto", 100, 100, 300, 50),
            ("Preço Inteiro", 120, 200, 120, 100),
            ("Preço Centavos", 245, 205, 70, 50),
        ]
    ):
        node = GraphicsNode(
            kind=NodeKind.TEXT,
            name=name,
            text=name,
            transform=Transform(x=x, y=y, width=width, height=height),
            z_index=index,
            metadata={"source_name": name},
        )
        page.add_node(node)
    return document


def test_rebuild_pptx_groups_restores_nested_parent_child_hierarchy(tmp_path):
    document = _document()
    source = _pptx(tmp_path / "groups.pptx")

    report = rebuild_pptx_groups(source, document)

    assert report.slides_scanned == 1
    assert report.groups_found == 2
    assert report.groups_rebuilt == 2
    assert report.nodes_reparented == 4
    page = document.active_page
    groups = {node.name: node for node in page.nodes.values() if node.kind is NodeKind.GROUP}
    assert set(groups) == {"Grupo Produto 1", "Grupo Preço"}
    outer = groups["Grupo Produto 1"]
    price = groups["Grupo Preço"]
    assert price.parent_id == outer.id
    assert price.id in outer.children
    name = next(node for node in page.nodes.values() if node.name == "Nome Produto")
    integer = next(node for node in page.nodes.values() if node.name == "Preço Inteiro")
    cents = next(node for node in page.nodes.values() if node.name == "Preço Centavos")
    assert name.parent_id == outer.id
    assert integer.parent_id == price.id
    assert cents.parent_id == price.id
    assert page.roots == [outer.id]
    assert not [issue for issue in run_preflight(document) if issue.severity == "error"]


def test_rebuild_pptx_groups_is_idempotent(tmp_path):
    document = _document()
    source = _pptx(tmp_path / "groups.pptx")
    first = rebuild_pptx_groups(source, document)
    first_group_count = sum(node.kind is NodeKind.GROUP for node in document.active_page.nodes.values())

    second = rebuild_pptx_groups(source, document)
    second_group_count = sum(node.kind is NodeKind.GROUP for node in document.active_page.nodes.values())

    assert first.groups_rebuilt == 2
    assert second.groups_rebuilt == 2
    assert first_group_count == second_group_count == 2
    page = document.active_page
    outer = next(node for node in page.nodes.values() if node.name == "Grupo Produto 1")
    assert page.roots == [outer.id]
