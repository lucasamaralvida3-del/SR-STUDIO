from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from srstudio.core.models import Page, StudioProject
from srstudio.graphics2 import import_bridge


def _known_canva_package(path: Path) -> Path:
    core = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/">
 <dc:identifier>DAHMLMj6EH8</dc:identifier>
 <cp:revision>1</cp:revision>
 <dcterms:created>2006-08-16T00:00:00Z</dcterms:created>
 <dcterms:modified>2011-08-01T06:04:30Z</dcterms:modified>
</cp:coreProperties>'''
    app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
 <Application>Microsoft Office PowerPoint</Application>
 <AppVersion>14.0000</AppVersion>
 <Slides>0</Slides>
 <PresentationFormat>On-screen Show (4:3)</PresentationFormat>
</Properties>'''
    presentation = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:sldSz cx="10287000" cy="12852400"/>
</p:presentation>'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("ppt/presentation.xml", presentation)
    return path


def test_graphics2_import_seam_changes_scene_only_and_preserves_bridge_metadata(tmp_path: Path) -> None:
    source = _known_canva_package(tmp_path / "known-canva.pptx")
    physical_height = 1080.0 * (12_852_400 / 10_287_000)
    project = StudioProject(
        name="Native canvas seam",
        pages=[Page(name="Slide 1", width=1080.0, height=physical_height)],
        settings={"pptx_source": str(source)},
    )

    document = import_bridge.from_imported_project(project)

    # The mature/shared StudioProject geometry is not rewritten by the G2 hook.
    assert project.pages[0].width == 1080.0
    assert project.pages[0].height == pytest.approx(1349.3333333333333)

    # SR Scene 2 receives the independently resolved intended Canva canvas.
    assert document.pages[0].width == 1080.0
    assert document.pages[0].height == 1350.0
    assert document.metadata["pptx_canvas_semantic_override_applied"] is True

    # Compatibility metadata from the historical branch is exposed by the G2
    # bridge without changing the shared importer implementation.
    assert project.settings["pptx_physical_page_size"] == {
        "width_emu": 10_287_000,
        "height_emu": 12_852_400,
        "width_pt": 810.0,
        "height_pt": 1012.0,
    }
    assert project.settings["intended_canvas_size"] == {"width": 1080.0, "height": 1350.0}
    assert project.settings["pptx_canvas_size_preset"] == "canva-4x5-1080x1350"
    assert project.settings["pptx_canvas_size_source"] == "canva"
    assert project.settings["pptx_source_profile"] == {
        "name": "canva-pptx-export-v1",
        "confidence": "reliable",
        "design_id": "DAHMLMj6EH8",
    }
    assert project.settings["pptx_canvas_size_evidence"]
