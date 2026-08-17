from __future__ import annotations

from zipfile import ZipFile

import pytest

from srstudio.core.models import Page
from srstudio.graphics2.import_bridge import GraphicsImportService
from srstudio.importers.pipeline import ImportSummary


PRESENTATION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="9144000" cy="11430000"/>
</p:presentation>
"""

UNIFORM_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="12" name="Preço principal"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      <p:txBody>
        <a:bodyPr><a:spAutoFit/></a:bodyPr><a:lstStyle/>
        <a:p>
          <a:pPr><a:lnSpc><a:spcPct val="125000"/></a:lnSpc></a:pPr>
          <a:r><a:rPr spc="240"/><a:t>25</a:t></a:r>
        </a:p>
      </p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

MIXED_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="13" name="Texto misto"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:r><a:rPr spc="100"/><a:t>A</a:t></a:r>
        <a:r><a:rPr spc="300"/><a:t>B</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""


def _write_pptx(path, slide_xml: str):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION_XML)
        archive.writestr("ppt/slides/slide1.xml", slide_xml)
    return path


class _FakePptxPipeline:
    def __init__(self, *, name: str, text: str):
        self.name = name
        self.text = text

    def import_file(self, path, project):
        project.pages = [
            Page(
                width=1080,
                height=1350,
                elements=[
                    {
                        "type": "text",
                        "name": self.name,
                        "x": 100,
                        "y": 100,
                        "width": 280,
                        "height": 120,
                        "text": self.text,
                        "font_name": "Arial",
                        "font_size": 72,
                        "source": "pptx",
                    }
                ],
            )
        ]
        return ImportSummary(str(path))


def test_graphics_import_pipeline_recovers_exact_spacing_before_mapping_gate(tmp_path):
    source = _write_pptx(tmp_path / "uniform.pptx", UNIFORM_SLIDE)
    service = GraphicsImportService()
    service.pipeline = _FakePptxPipeline(name="Preço principal", text="25")

    result = service.import_file(source, project_name="Spacing pipeline")
    node = next(node for node in result.document.active_page.nodes.values() if node.name == "Preço principal")
    recovery = result.document.metadata["pptx_spacing_recovery"]
    mapping = result.document.metadata["pptx_mapping_audit"]

    assert recovery["letter_spacing_coverage"] == 1.0
    assert recovery["line_spacing_coverage"] == 1.0
    assert node.style["letter_spacing_pt"] == pytest.approx(2.4)
    assert node.style["letter_spacing"] == pytest.approx(3.2)
    assert node.style["line_spacing_percent"] == pytest.approx(125.0)
    assert mapping["letter_spacing_coverage"] == 1.0
    assert mapping["line_spacing_coverage"] == 1.0


def test_graphics_import_pipeline_does_not_report_mixed_run_spacing_as_exact(tmp_path):
    source = _write_pptx(tmp_path / "mixed.pptx", MIXED_SLIDE)
    service = GraphicsImportService()
    service.pipeline = _FakePptxPipeline(name="Texto misto", text="AB")

    result = service.import_file(source, project_name="Mixed spacing pipeline")
    node = next(node for node in result.document.active_page.nodes.values() if node.name == "Texto misto")
    recovery = result.document.metadata["pptx_spacing_recovery"]
    mapping = result.document.metadata["pptx_mapping_audit"]

    assert recovery["letter_spacing_coverage"] == 0.0
    assert any(issue["code"] == "PPTX_LETTER_SPACING_MIXED" for issue in recovery["issues"])
    assert "letter_spacing" not in node.style
    assert "letter_spacing_pt" not in node.style
    assert mapping["letter_spacing_coverage"] == 0.0
