from __future__ import annotations

from zipfile import ZipFile

from srstudio.importers.pptx.package_order import ordered_slide_paths
from srstudio.importers.pptx.reader import PptxImporter


PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="257" r:id="rIdSecond"/>
    <p:sldId id="256" r:id="rIdFirst"/>
  </p:sldIdLst>
  <p:sldSz cx="1000" cy="1000"/>
</p:presentation>
"""

PRESENTATION_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdFirst" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rIdSecond" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>
</Relationships>
"""


def _slide(label: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="{label}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm></p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{label}</a:t></a:r></a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""


def _write_reordered(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/_rels/presentation.xml.rels", PRESENTATION_RELS)
        archive.writestr("ppt/slides/slide1.xml", _slide("FILE ONE"))
        archive.writestr("ppt/slides/slide2.xml", _slide("FILE TWO"))
    return path


def test_ordered_slide_paths_uses_presentation_relationship_order(tmp_path):
    path = _write_reordered(tmp_path / "reordered.pptx")
    with ZipFile(path) as archive:
        assert ordered_slide_paths(archive) == [
            "ppt/slides/slide2.xml",
            "ppt/slides/slide1.xml",
        ]


def test_pptx_importer_assigns_scene_page_indices_from_logical_order(tmp_path):
    result = PptxImporter().import_file(_write_reordered(tmp_path / "reader-order.pptx"))

    assert [slide.index for slide in result.slides] == [1, 2]
    assert result.slides[0].elements[0].text == "FILE TWO"
    assert result.slides[0].elements[0].name == "FILE TWO"
    assert result.slides[1].elements[0].text == "FILE ONE"
    assert result.slides[1].elements[0].name == "FILE ONE"


def test_order_helper_falls_back_to_numeric_parts_for_minimal_fixture(tmp_path):
    path = tmp_path / "minimal.pptx"
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide10.xml", _slide("TEN"))
        archive.writestr("ppt/slides/slide2.xml", _slide("TWO"))
    with ZipFile(path) as archive:
        assert ordered_slide_paths(archive) == [
            "ppt/slides/slide2.xml",
            "ppt/slides/slide10.xml",
        ]


def test_order_helper_keeps_unreferenced_slide_parts_deterministically(tmp_path):
    path = tmp_path / "orphan.pptx"
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/_rels/presentation.xml.rels", PRESENTATION_RELS)
        archive.writestr("ppt/slides/slide1.xml", _slide("ONE"))
        archive.writestr("ppt/slides/slide2.xml", _slide("TWO"))
        archive.writestr("ppt/slides/slide3.xml", _slide("ORPHAN"))
    with ZipFile(path) as archive:
        assert ordered_slide_paths(archive) == [
            "ppt/slides/slide2.xml",
            "ppt/slides/slide1.xml",
            "ppt/slides/slide3.xml",
        ]
