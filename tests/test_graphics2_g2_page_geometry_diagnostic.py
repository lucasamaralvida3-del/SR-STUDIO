from __future__ import annotations

from types import SimpleNamespace
import zipfile

import pytest

from srstudio.graphics2.model import CoordinateUnit, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.pptx_page_geometry_runtime import install_pptx_page_geometry_guard
from srstudio.graphics2.pptx_source_profile import (
    CANVA_4X5_PHYSICAL_EMU,
    apply_pptx_page_geometry,
    inspect_pptx_source_profile,
)
from srstudio.graphics2.qt_renderer import _raster_scale


CANVA_WIDTH_EMU, CANVA_HEIGHT_EMU = CANVA_4X5_PHYSICAL_EMU


def _write_profile_pptx(
    path,
    *,
    design_id: str = "DAHMLMj6EH8",
    width_emu: int = CANVA_WIDTH_EMU,
    height_emu: int = CANVA_HEIGHT_EMU,
    canva_fingerprint: bool = True,
) -> None:
    created = "2006-08-16T00:00:00Z" if canva_fingerprint else "2026-08-18T12:00:00Z"
    modified = "2011-08-01T06:04:30Z" if canva_fingerprint else "2026-08-18T12:30:00Z"
    revision = "1" if canva_fingerprint else "8"
    app_version = "14.0000" if canva_fingerprint else "16.0000"
    slides = "0" if canva_fingerprint else "3"
    presentation_format = "On-screen Show (4:3)" if canva_fingerprint else "Custom"

    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <dc:identifier>{design_id}</dc:identifier>
 <cp:revision>{revision}</cp:revision>
 <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
 <dcterms:modified xsi:type="dcterms:W3CDTF">{modified}</dcterms:modified>
</cp:coreProperties>"""
    app = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
 <Application>Microsoft Office PowerPoint</Application>
 <AppVersion>{app_version}</AppVersion>
 <Slides>{slides}</Slides>
 <PresentationFormat>{presentation_format}</PresentationFormat>
</Properties>"""
    presentation = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:sldSz cx="{width_emu}" cy="{height_emu}"/>
</p:presentation>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("ppt/presentation.xml", presentation)


def _physical_ratio_page(*, height_emu: int = CANVA_HEIGHT_EMU) -> GraphicsPage:
    return GraphicsPage(
        name="Imported PPTX",
        width=1080.0,
        height=1080.0 * height_emu / CANVA_WIDTH_EMU,
        unit=CoordinateUnit.PIXEL,
    )


def test_known_canva_4x5_uses_intended_1080x1350_and_keeps_physical_size(tmp_path) -> None:
    source = tmp_path / "canva-known.pptx"
    _write_profile_pptx(source)
    profile = inspect_pptx_source_profile(source)

    page = _physical_ratio_page()
    node = GraphicsNode(
        kind=NodeKind.RECT,
        transform=Transform(x=100.0, y=100.0, width=200.0, height=300.0),
    )
    page.add_node(node)
    document = GraphicsDocument(pages=[page])

    assert profile.name == "canva"
    assert profile.confidence == "reliable"
    assert profile.reliable_canva is True
    assert profile.design_id == "DAHMLMj6EH8"
    assert profile.physical_page_size is not None
    assert profile.physical_page_size.width_emu == CANVA_WIDTH_EMU
    assert profile.physical_page_size.height_emu == CANVA_HEIGHT_EMU
    assert profile.physical_page_size.width_pt == pytest.approx(810.0)
    assert profile.physical_page_size.height_pt == pytest.approx(1012.0)
    assert profile.intended_canvas_size is not None

    old_y = node.transform.y
    old_h = node.transform.height
    old_page_height = page.height
    assert apply_pptx_page_geometry(document, profile) is True

    assert page.width == 1080.0
    assert page.height == 1350.0
    assert node.transform.y == pytest.approx(old_y * 1350.0 / old_page_height)
    assert node.transform.height == pytest.approx(old_h * 1350.0 / old_page_height)
    assert page.metadata["physical_page_size"]["width_emu"] == CANVA_WIDTH_EMU
    assert page.metadata["physical_page_size"]["height_emu"] == CANVA_HEIGHT_EMU
    assert page.metadata["intended_canvas_size"] == {"width": 1080.0, "height": 1350.0}
    assert page.metadata["source_profile"]["name"] == "canva"
    assert page.metadata["source_profile"]["confidence"] == "reliable"


def test_generic_non_canva_pptx_preserves_physical_aspect_ratio(tmp_path) -> None:
    source = tmp_path / "generic-office.pptx"
    width_emu = 9_144_000
    height_emu = 6_858_000
    _write_profile_pptx(
        source,
        design_id="office-document-42",
        width_emu=width_emu,
        height_emu=height_emu,
        canva_fingerprint=False,
    )
    profile = inspect_pptx_source_profile(source)
    page = GraphicsPage(width=1080.0, height=1080.0 * height_emu / width_emu)
    document = GraphicsDocument(pages=[page])

    assert profile.reliable_canva is False
    assert profile.intended_canvas_size is None
    assert apply_pptx_page_geometry(document, profile) is False
    assert page.width == 1080.0
    assert page.height == pytest.approx(810.0)
    assert page.metadata["physical_page_size"]["width_emu"] == width_emu
    assert page.metadata["physical_page_size"]["height_emu"] == height_emu


def test_aspect_ratio_alone_never_classifies_generic_4x5_as_canva(tmp_path) -> None:
    source = tmp_path / "generic-4x5.pptx"
    _write_profile_pptx(
        source,
        design_id="generic-4x5-office",
        canva_fingerprint=False,
    )
    profile = inspect_pptx_source_profile(source)

    assert profile.physical_page_size is not None
    assert (profile.physical_page_size.width_emu, profile.physical_page_size.height_emu) == CANVA_4X5_PHYSICAL_EMU
    assert profile.reliable_canva is False
    assert profile.intended_canvas_size is None


def test_canva_identifier_without_full_fingerprint_is_partial_and_does_not_override(tmp_path) -> None:
    source = tmp_path / "partial-canva.pptx"
    _write_profile_pptx(source, canva_fingerprint=False)
    profile = inspect_pptx_source_profile(source)
    page = _physical_ratio_page()
    original_height = page.height

    assert profile.name == "canva"
    assert profile.confidence == "partial"
    assert profile.reliable_canva is False
    assert profile.intended_canvas_size is None
    assert apply_pptx_page_geometry(GraphicsDocument(pages=[page]), profile) is False
    assert page.height == pytest.approx(original_height)


def test_reliable_canva_arbitrary_physical_page_is_not_forced_to_4x5_preset(tmp_path) -> None:
    source = tmp_path / "canva-arbitrary.pptx"
    width_emu = 9_144_000
    height_emu = 5_143_500
    _write_profile_pptx(source, width_emu=width_emu, height_emu=height_emu)
    profile = inspect_pptx_source_profile(source)
    page = GraphicsPage(width=1080.0, height=1080.0 * height_emu / width_emu)
    original_height = page.height

    assert profile.reliable_canva is True
    assert profile.intended_canvas_size is None
    assert apply_pptx_page_geometry(GraphicsDocument(pages=[page]), profile) is False
    assert page.height == pytest.approx(original_height)


def test_target_width_uses_intended_canva_aspect_ratio() -> None:
    page = GraphicsPage(
        name="Canva intended canvas",
        width=1080.0,
        height=1350.0,
        unit=CoordinateUnit.PIXEL,
    )

    scale = _raster_scale(page, dpi=300, target_width=1229)
    assert scale == pytest.approx(1229 / 1080)
    assert round(page.width * scale) == 1229
    assert round(page.height * scale) == 1536


def test_g2_runtime_hook_applies_canvas_after_shared_import_without_mutating_source_project(tmp_path) -> None:
    source = tmp_path / "canva-runtime.pptx"
    _write_profile_pptx(source)
    page = _physical_ratio_page()
    document = GraphicsDocument(pages=[page])
    fake_bridge = SimpleNamespace(from_imported_project=lambda _project: document)
    install_pptx_page_geometry_guard(fake_bridge)
    project = SimpleNamespace(settings={"pptx_source": str(source)})

    result = fake_bridge.from_imported_project(project)

    assert result is document
    assert page.width == 1080.0
    assert page.height == 1350.0
    assert project.settings == {"pptx_source": str(source)}
