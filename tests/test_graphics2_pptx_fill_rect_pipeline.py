from __future__ import annotations

from zipfile import ZipFile

from PIL import Image
import pytest

from srstudio.core.models import Page
from srstudio.graphics2.import_bridge import GraphicsImportService
from srstudio.graphics2.quality import inspect_production_gate
from srstudio.importers.pipeline import ImportSummary


PRESENTATION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="9144000" cy="11430000"/>
</p:presentation>
"""

SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="7" name="Freeform 7"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:blipFill><a:blip r:embed="rId7"/><a:stretch><a:fillRect l="-52421" t="0" r="-31438" b="0"/></a:stretch></a:blipFill>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
      </p:spPr>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""


def _write_pptx(path):
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION_XML)
        archive.writestr("ppt/slides/slide1.xml", SLIDE)
    return path


def _image(path):
    Image.new("RGB", (40, 30), "white").save(path)
    return path


class _FakeImagePipeline:
    def __init__(self, image_path, *, duplicate=False):
        self.image_path = image_path
        self.duplicate = duplicate

    def import_file(self, path, project):
        elements = [
            {
                "type": "image",
                "name": "Freeform 7",
                "path": str(self.image_path),
                "x": 100,
                "y": 100,
                "width": 300,
                "height": 180,
                "source": "pptx",
                "fill_rect": {"l": -0.1, "t": 0, "r": -0.1, "b": 0},
                "image_fit": "cover",
            }
        ]
        if self.duplicate:
            elements.append(
                {
                    "type": "image",
                    "name": "Freeform 7",
                    "path": str(self.image_path),
                    "x": 450,
                    "y": 100,
                    "width": 300,
                    "height": 180,
                    "source": "pptx",
                    "fill_rect": {"l": -0.1, "t": 0, "r": -0.1, "b": 0},
                    "image_fit": "cover",
                }
            )
        project.pages = [Page(width=1080, height=1350, elements=elements)]
        return ImportSummary(str(path))


def test_import_pipeline_corrects_wrong_fill_rect_before_exact_mapping_gate(tmp_path):
    source = _write_pptx(tmp_path / "fill-exact.pptx")
    service = GraphicsImportService()
    service.pipeline = _FakeImagePipeline(_image(tmp_path / "product.png"))

    result = service.import_file(source, project_name="Exact fillRect")
    node = next(node for node in result.document.active_page.nodes.values() if node.name == "Freeform 7")
    recovery = result.document.metadata["pptx_fill_rect_recovery"]
    mapping = result.document.metadata["pptx_mapping_audit"]

    assert recovery["corrected_contracts"] == 1
    assert recovery["coverage"] == 1.0
    assert recovery["outset_coverage"] == 1.0
    assert node.style["fill_rect"] == pytest.approx({"l": -0.52421, "t": 0.0, "r": -0.31438, "b": 0.0})
    assert mapping["source_fill_rects"] == 1
    assert mapping["imported_fill_rects"] == 1
    assert mapping["fill_rect_coverage"] == 1.0
    assert mapping["source_fill_outsets"] == 1
    assert mapping["imported_fill_outsets"] == 1
    assert mapping["fill_outset_coverage"] == 1.0


def test_import_pipeline_does_not_fake_exact_fill_coverage_when_shape_is_ambiguous(tmp_path):
    source = _write_pptx(tmp_path / "fill-ambiguous.pptx")
    service = GraphicsImportService()
    service.pipeline = _FakeImagePipeline(_image(tmp_path / "product.png"), duplicate=True)

    result = service.import_file(source, project_name="Ambiguous fillRect")
    recovery = result.document.metadata["pptx_fill_rect_recovery"]
    mapping = result.document.metadata["pptx_mapping_audit"]
    gate = inspect_production_gate(result.document, require_visual_fidelity=False)

    assert recovery["mapped_contracts"] == 0
    assert recovery["coverage"] == 0.0
    assert any(issue["code"] == "PPTX_FILL_RECT_SHAPE_AMBIGUOUS" for issue in recovery["issues"])
    assert mapping["fill_rect_coverage"] == 0.0
    assert mapping["fill_outset_coverage"] == 0.0
    assert any(issue.code == "PPTX_FILL_RECT_COVERAGE_FAILED" for issue in gate.issues)
    assert any(issue.code == "PPTX_FILL_OUTSET_COVERAGE_FAILED" for issue in gate.issues)
