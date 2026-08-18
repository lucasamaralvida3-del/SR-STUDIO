from __future__ import annotations

from zipfile import ZipFile

from srstudio.graphics2.image_crop import normalize_crop
from srstudio.graphics2.import_bridge import _element_to_node
from srstudio.graphics2.model import GraphicsDocument, NodeKind
from srstudio.importers.pipeline import ImportPipeline
from srstudio.importers.pptx.reader import PptxImporter


PRESENTATION = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="100" cy="100"/>
</p:presentation>
"""

SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="7" name="Crop assinado"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill>
        <a:blip r:embed="rId7"/>
        <a:srcRect l="-12000" t="25000" r="5000" b="-3000"/>
        <a:stretch><a:fillRect/></a:stretch>
      </p:blipFill>
      <p:spPr><a:xfrm><a:off x="10" y="20"/><a:ext cx="30" cy="40"/></a:xfrm></p:spPr>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>
"""

SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
</Relationships>
"""


def _pptx(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/slides/slide1.xml", SLIDE)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", SLIDE_RELS)
        # O leitor só precisa preservar/extrair o payload neste teste; não há
        # rasterização. Um cabeçalho PNG mínimo é suficiente para o caminho.
        archive.writestr("ppt/media/image1.png", b"\x89PNG\r\n\x1a\n")
    return path


def test_signed_src_rect_survives_reader_pipeline_and_scene_conversion(tmp_path):
    source = _pptx(tmp_path / "signed-src-rect.pptx")
    imported = PptxImporter().import_file(source, media_dir=tmp_path / "media")
    slide = imported.slides[0]
    element = slide.elements[0]

    assert element.metadata["crop"] == {
        "l": -0.12,
        "t": 0.25,
        "r": 0.05,
        "b": -0.03,
    }

    legacy = ImportPipeline._pptx_element(element, slide.width, slide.height, 100, 100)
    assert legacy is not None
    assert legacy["crop"] == element.metadata["crop"]

    document = GraphicsDocument(name="signed crop")
    node = _element_to_node(document, legacy, 0)
    assert node is not None
    assert node.kind is NodeKind.IMAGE
    assert node.style["crop"] == element.metadata["crop"]

    # Delimita a fronteira do bug: a SR Scene ainda contém os outsets negativos
    # corretos; a normalização visual atual é que os clampa para zero.
    visual_crop = normalize_crop(node.style["crop"])
    assert visual_crop.left == 0.0
    assert visual_crop.top == 0.25
    assert visual_crop.right == 0.05
    assert visual_crop.bottom == 0.0
