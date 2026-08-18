from __future__ import annotations

from zipfile import ZipFile

from srstudio.core.models import Page
from srstudio.graphics2.import_bridge import GraphicsImportService
from srstudio.importers.pipeline import ImportSummary


PRESENTATION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="9144000" cy="11430000"/>
</p:presentation>
"""

SLIDE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="42" name="Texto Canva"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/>
        <a:p><a:r><a:rPr spc="100"/><a:t xml:space="preserve"> OFERTA </a:t></a:r></a:p>
        <a:p/>
        <a:p><a:r><a:rPr spc="100"/><a:t>R$ 9,99</a:t></a:r></a:p>
      </p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""


def _write_pptx(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION_XML)
        archive.writestr("ppt/slides/slide1.xml", SLIDE_XML)
    return path


class _NormalizedLegacyPipeline:
    def import_file(self, path, project):
        # Reproduz o contrato legado: parágrafo vazio descartado e whitespace
        # significativo normalizado antes da conversão para SR Scene 2.
        project.pages = [
            Page(
                width=1080,
                height=1350,
                elements=[
                    {
                        "type": "text",
                        "name": "Texto Canva",
                        "x": 100,
                        "y": 100,
                        "width": 400,
                        "height": 160,
                        "text": "OFERTA\nR$ 9,99",
                        "font_name": "Arial",
                        "font_size": 72,
                        "source": "pptx",
                    }
                ],
            )
        ]
        return ImportSummary(str(path))


def test_graphics_import_service_restores_exact_ooxml_text_before_mapping_audit(tmp_path):
    source = _write_pptx(tmp_path / "canva-text.pptx")
    service = GraphicsImportService()
    service.pipeline = _NormalizedLegacyPipeline()

    result = service.import_file(source, project_name="Canva text")
    node = next(node for node in result.document.active_page.nodes.values() if node.name == "Texto Canva")
    recovery = result.document.metadata["pptx_text_content_recovery"]

    assert node.text == " OFERTA \n\nR$ 9,99"
    assert node.metadata["pptx_text_content_previous"] == "OFERTA\nR$ 9,99"
    assert node.metadata["pptx_shape_id"] == "42"
    assert recovery["source_contracts"] == 1
    assert recovery["mapped_contracts"] == 1
    assert recovery["exact_contracts"] == 1
    assert recovery["corrected_contracts"] == 1
    assert recovery["coverage"] == 1.0
