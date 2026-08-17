from __future__ import annotations

from zipfile import ZipFile

from PIL import Image

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
      <p:nvSpPr><p:cNvPr id="3" name="Freeform 3"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:xfrm rot="-10800000"><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm>
        <a:blipFill><a:blip r:embed="rId3"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>
      </p:spPr>
    </p:sp>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="4" name="Freeform 4"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm>
        <a:blipFill><a:blip r:embed="rId4"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>
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
    def __init__(self, image_path, *, duplicate_special=False):
        self.image_path = image_path
        self.duplicate_special = duplicate_special

    def import_file(self, path, project):
        elements = [
            {
                "type": "image",
                "name": "Freeform 3",
                "path": str(self.image_path),
                "x": 100,
                "y": 100,
                "width": 220,
                "height": 150,
                "rotation": 0,
                "source": "pptx",
                "fill_rect": {"l": 0, "t": 0, "r": 0, "b": 0},
                "image_fit": "cover",
            },
            {
                "type": "image",
                "name": "Freeform 4",
                "path": str(self.image_path),
                "x": 360,
                "y": 100,
                "width": 220,
                "height": 150,
                "rotation": 0,
                "source": "pptx",
                "fill_rect": {"l": 0, "t": 0, "r": 0, "b": 0},
                "image_fit": "cover",
            },
        ]
        if self.duplicate_special:
            elements.append(
                {
                    "type": "image",
                    "name": "Freeform 3",
                    "path": str(self.image_path),
                    "x": 620,
                    "y": 100,
                    "width": 220,
                    "height": 150,
                    "rotation": 0,
                    "source": "pptx",
                    "fill_rect": {"l": 0, "t": 0, "r": 0, "b": 0},
                    "image_fit": "cover",
                }
            )
        project.pages = [Page(width=1080, height=1350, elements=elements)]
        return ImportSummary(str(path))


def test_import_pipeline_restores_quinta_file_minus_180_image_rotation(tmp_path):
    source = _write_pptx(tmp_path / "rotation.pptx")
    service = GraphicsImportService()
    service.pipeline = _FakeImagePipeline(_image(tmp_path / "product.png"))

    result = service.import_file(source, project_name="Quinta rotation")
    special = next(node for node in result.document.active_page.nodes.values() if node.name == "Freeform 3")
    normal = next(node for node in result.document.active_page.nodes.values() if node.name == "Freeform 4")
    recovery = result.document.metadata["pptx_image_transform_recovery"]
    gate = inspect_production_gate(result.document, require_visual_fidelity=False)

    assert special.transform.rotation == -180.0
    assert normal.transform.rotation == 0.0
    assert recovery["source_contracts"] == 2
    assert recovery["non_identity_contracts"] == 1
    assert recovery["exact_contracts"] == 2
    assert recovery["exact_non_identity_contracts"] == 1
    assert recovery["coverage"] == 1.0
    assert recovery["non_identity_coverage"] == 1.0
    assert gate.image_transform_coverage == 1.0
    assert gate.image_transform_non_identity_coverage == 1.0
    assert not any(issue.code.startswith("PPTX_IMAGE_TRANSFORM_") for issue in gate.issues)


def test_import_pipeline_blocks_when_special_rotation_shape_is_ambiguous(tmp_path):
    source = _write_pptx(tmp_path / "rotation-ambiguous.pptx")
    service = GraphicsImportService()
    service.pipeline = _FakeImagePipeline(_image(tmp_path / "product.png"), duplicate_special=True)

    result = service.import_file(source, project_name="Quinta rotation ambiguous")
    recovery = result.document.metadata["pptx_image_transform_recovery"]
    gate = inspect_production_gate(result.document, require_visual_fidelity=False)

    assert recovery["non_identity_contracts"] == 1
    assert recovery["exact_non_identity_contracts"] == 0
    assert recovery["non_identity_coverage"] == 0.0
    assert any(issue["code"] == "PPTX_IMAGE_TRANSFORM_SHAPE_AMBIGUOUS" for issue in recovery["issues"])
    assert any(issue.code == "PPTX_IMAGE_TRANSFORM_NON_IDENTITY_FAILED" for issue in gate.issues)
