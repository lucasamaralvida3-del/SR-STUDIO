from __future__ import annotations

from pathlib import Path
import struct
import zipfile

import pytest

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_fidelity import enhance_pptx_document


PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="10287000" cy="12852400"/>
  <p:embeddedFontLst>
    <p:embeddedFont>
      <p:font typeface="Anton" charset="1"/>
      <p:regular r:id="rIdFont"/>
    </p:embeddedFont>
  </p:embeddedFontLst>
</p:presentation>
"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdFont" Target="fonts/font1.fntdata"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"/>
</Relationships>
"""

SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:cSld><p:spTree>
   <p:nvGrpSpPr/><p:grpSpPr/>
   <p:sp>
     <p:nvSpPr><p:cNvPr id="2" name="Text Box 1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
     <p:spPr><a:xfrm><a:off x="914400" y="914400"/><a:ext cx="2743200" cy="457200"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
     <p:txBody>
       <a:bodyPr lIns="91440" tIns="45720" rIns="91440" bIns="45720" anchor="t"><a:spAutoFit/></a:bodyPr>
       <a:lstStyle/>
       <a:p><a:pPr algn="ctr"><a:lnSpc><a:spcPts val="1200"/></a:lnSpc></a:pPr><a:r><a:rPr sz="2400" spc="-55"><a:latin typeface="Anton"/></a:rPr><a:t>ACÉM BOVINO</a:t></a:r></a:p>
     </p:txBody>
   </p:sp>
   <p:sp>
     <p:nvSpPr><p:cNvPr id="3" name="Freeform 1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
     <p:spPr>
       <a:xfrm><a:off x="914400" y="1828800"/><a:ext cx="1828800" cy="914400"/></a:xfrm>
       <a:solidFill><a:srgbClr val="470000"/></a:solidFill>
       <a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/>
         <a:pathLst><a:path w="1000" h="500">
           <a:moveTo><a:pt x="100" y="0"/></a:moveTo>
           <a:lnTo><a:pt x="900" y="0"/></a:lnTo>
           <a:cubicBezTo><a:pt x="955" y="0"/><a:pt x="1000" y="45"/><a:pt x="1000" y="100"/></a:cubicBezTo>
           <a:lnTo><a:pt x="1000" y="400"/></a:lnTo>
           <a:cubicBezTo><a:pt x="1000" y="455"/><a:pt x="955" y="500"/><a:pt x="900" y="500"/></a:cubicBezTo>
           <a:lnTo><a:pt x="100" y="500"/></a:lnTo>
           <a:cubicBezTo><a:pt x="45" y="500"/><a:pt x="0" y="455"/><a:pt x="0" y="400"/></a:cubicBezTo>
           <a:lnTo><a:pt x="0" y="100"/></a:lnTo>
           <a:cubicBezTo><a:pt x="0" y="45"/><a:pt x="45" y="0"/><a:pt x="100" y="0"/></a:cubicBezTo>
           <a:close/>
         </a:path></a:pathLst>
       </a:custGeom>
     </p:spPr>
   </p:sp>
 </p:spTree></p:cSld>
</p:sld>
"""


def _fake_eot() -> bytes:
    # SFNT mínimo suficiente para validar a extração do payload EOT no teste.
    payload = b"\x00\x01\x00\x00" + b"\x00" * 28
    header_size = 16
    total = header_size + len(payload)
    return struct.pack("<II", total, len(payload)) + b"\x00" * 8 + payload


def _pptx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/_rels/presentation.xml.rels", RELS)
        archive.writestr("ppt/slides/slide1.xml", SLIDE)
        archive.writestr("ppt/fonts/font1.fntdata", _fake_eot())
    return path


def _document() -> GraphicsDocument:
    document = GraphicsDocument(name="PPTX Fidelity")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Text Box 1",
        text="ACÉM BOVINO",
        transform=Transform(x=96, y=96, width=288, height=48),
        style={"font_family": "Impact", "source_font_family": "Anton", "font_size": 24, "nowrap": True},
        metadata={"source_name": "Text Box 1", "source_font_name": "Anton"},
    )
    shape = GraphicsNode(
        kind=NodeKind.RECT,
        name="Freeform 1",
        transform=Transform(x=96, y=192, width=192, height=96),
        style={"fill": "#470000", "stroke": "transparent"},
        metadata={"source_name": "Freeform 1"},
    )
    page.add_node(text)
    page.add_node(shape)
    return document


def test_pptx_fidelity_extracts_embedded_font_and_exact_custom_path(tmp_path):
    source = _pptx(tmp_path / "canva.pptx")
    document = _document()

    report = enhance_pptx_document(source, document, cache_dir=tmp_path / "cache")

    assert report.fonts_declared == 1
    assert report.fonts_extracted == 1
    assert report.text_nodes_enriched == 1
    assert report.custom_paths_enriched == 1
    assert not report.warnings

    text = next(node for node in document.active_page.nodes.values() if node.name == "Text Box 1")
    assert text.style["font_family"] == "Anton"
    assert text.style["fit_inside_box"] is True
    assert text.style["pptx_auto_fit"] == "shape"
    assert text.style["letter_spacing_pt"] == pytest.approx(-0.55)
    assert text.style["line_spacing_pt"] == pytest.approx(12.0)
    assert text.style["text_insets"]["left"] == pytest.approx(9.6, rel=0.01)
    assert Path(text.metadata["embedded_font_path"]).is_file()

    shape = next(node for node in document.active_page.nodes.values() if node.name == "Freeform 1")
    spec = shape.metadata["custom_path"]
    assert spec["width"] == 1000
    assert spec["height"] == 500
    assert any(command["op"] == "C" for command in spec["paths"][0]["commands"])
    assert document.metadata["pptx_fidelity"]["custom_paths_enriched"] == 1
