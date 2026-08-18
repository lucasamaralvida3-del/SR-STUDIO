from __future__ import annotations

from zipfile import ZipFile

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_text_content import recover_pptx_text_content


SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="7" name="Texto exato"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:txBody><a:bodyPr/><a:lstStyle/>
        <a:p><a:r><a:t xml:space="preserve">  Preço </a:t></a:r></a:p>
        <a:p/>
        <a:p><a:r><a:t>Linha</a:t></a:r><a:br/><a:r><a:t xml:space="preserve"> final  </a:t></a:r></a:p>
      </p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

NESTED_GROUP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:grpSp>
      <p:nvGrpSpPr><p:cNvPr id="20" name="Grupo 1"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:grpSp>
        <p:nvGrpSpPr><p:cNvPr id="21" name="Grupo 2"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
        <p:grpSpPr/>
        <p:sp>
          <p:nvSpPr><p:cNvPr id="22" name="Texto agrupado"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Grupo</a:t></a:r></a:p></p:txBody>
        </p:sp>
      </p:grpSp>
    </p:grpSp>
  </p:spTree></p:cSld>
</p:sld>
"""

SECOND_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="31" name="Mesmo nome"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p/><a:p><a:r><a:t>Slide 2</a:t></a:r></a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

FIRST_SLIDE = SECOND_SLIDE.replace("Slide 2", "Slide 1").replace('id="31"', 'id="30"')


def _pptx(path, *slides: str):
    with ZipFile(path, "w") as archive:
        for index, xml in enumerate(slides or (SLIDE,), start=1):
            archive.writestr(f"ppt/slides/slide{index}.xml", xml)
    return path


def _text(node_id: str, name: str, text: str = "normalizado") -> GraphicsNode:
    return GraphicsNode(
        id=node_id,
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        transform=Transform(width=200, height=80),
        metadata={"source": "pptx", "source_name": name},
    )


def test_preserves_boundary_whitespace_empty_paragraphs_and_inline_breaks(tmp_path):
    document = GraphicsDocument(name="exact text")
    document.active_page.add_node(_text("text", "Texto exato", "Preço\nLinha final"))

    report = recover_pptx_text_content(_pptx(tmp_path / "exact.pptx", SLIDE), document)
    node = document.active_page.node("text")

    assert report.source_contracts == 1
    assert report.mapped_contracts == 1
    assert report.exact_contracts == 1
    assert report.corrected_contracts == 1
    assert report.contracts_with_empty_paragraphs == 1
    assert report.contracts_with_inline_breaks == 1
    assert report.contracts_with_boundary_whitespace == 1
    assert report.coverage == 1.0
    assert node.text == "  Preço \n\nLinha\n final  "
    assert node.metadata["pptx_text_content_previous"] == "Preço\nLinha final"
    assert node.metadata["pptx_text_content"] == {
        "paragraph_count": 3,
        "empty_paragraphs": 1,
        "inline_breaks": 1,
        "tabs": 0,
        "significant_boundary_whitespace": True,
    }


def test_recovers_text_inside_nested_groups_without_guessing_group_geometry(tmp_path):
    document = GraphicsDocument(name="nested text")
    document.active_page.add_node(_text("nested", "Texto agrupado", "errado"))

    report = recover_pptx_text_content(_pptx(tmp_path / "nested.pptx", NESTED_GROUP), document)

    assert report.source_contracts == 1
    assert report.exact_contracts == 1
    assert document.active_page.node("nested").text == "Grupo"
    assert document.active_page.node("nested").metadata["pptx_shape_id"] == "22"


def test_maps_same_shape_name_independently_per_slide(tmp_path):
    document = GraphicsDocument(name="multi slide")
    page1 = document.pages[0]
    page2 = document.add_page()
    page1.add_node(_text("slide1", "Mesmo nome", "Slide 1"))
    page2.add_node(_text("slide2", "Mesmo nome", "Slide 2"))

    report = recover_pptx_text_content(
        _pptx(tmp_path / "multi.pptx", FIRST_SLIDE, SECOND_SLIDE),
        document,
    )

    assert report.source_contracts == 2
    assert report.mapped_contracts == 2
    assert report.exact_contracts == 2
    assert page1.node("slide1").text == "\nSlide 1"
    assert page2.node("slide2").text == "\nSlide 2"
    assert page1.node("slide1").metadata["pptx_shape_id"] == "30"
    assert page2.node("slide2").metadata["pptx_shape_id"] == "31"


def test_ambiguous_scene_mapping_is_reported_without_mutation(tmp_path):
    document = GraphicsDocument(name="ambiguous text")
    page = document.active_page
    page.add_node(_text("one", "Texto exato", "um"))
    page.add_node(_text("two", "Texto exato", "dois"))

    report = recover_pptx_text_content(_pptx(tmp_path / "ambiguous.pptx", SLIDE), document)

    assert report.source_contracts == 1
    assert report.mapped_contracts == 0
    assert report.exact_contracts == 0
    assert page.node("one").text == "um"
    assert page.node("two").text == "dois"
    assert any(issue.code == "PPTX_TEXT_CONTENT_SHAPE_AMBIGUOUS" for issue in report.issues)
