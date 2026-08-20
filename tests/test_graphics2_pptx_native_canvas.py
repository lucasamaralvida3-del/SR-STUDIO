from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import zipfile

import pytest

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.pptx_native_canvas import (
    CANVA_4X5_PRESET,
    CANVA_4X5_PHYSICAL_EMU,
    resolve_pptx_native_canvas,
)
from srstudio.graphics2.pptx_native_canvas_runtime import apply_pptx_native_canvas
from srstudio.graphics2.qt_renderer import _raster_scale


def _pptx_fixture(
    path: Path,
    *,
    design_id: str = "DAHMLMj6EH8",
    width_emu: int = CANVA_4X5_PHYSICAL_EMU[0],
    height_emu: int = CANVA_4X5_PHYSICAL_EMU[1],
    fingerprint: bool = True,
) -> Path:
    created = "2006-08-16T00:00:00Z" if fingerprint else "2026-08-18T00:00:00Z"
    modified = "2011-08-01T06:04:30Z" if fingerprint else "2026-08-18T00:00:00Z"
    revision = "1" if fingerprint else "9"
    application = "Microsoft Office PowerPoint"
    version = "14.0000" if fingerprint else "16.0000"
    slides = "0" if fingerprint else "1"
    presentation_format = "On-screen Show (4:3)" if fingerprint else "Custom"
    identifier = f"<dc:identifier>{design_id}</dc:identifier>" if design_id else ""

    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/">
 {identifier}
 <cp:revision>{revision}</cp:revision>
 <dcterms:created>{created}</dcterms:created>
 <dcterms:modified>{modified}</dcterms:modified>
</cp:coreProperties>'''
    app = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
 <Application>{application}</Application>
 <AppVersion>{version}</AppVersion>
 <Slides>{slides}</Slides>
 <PresentationFormat>{presentation_format}</PresentationFormat>
</Properties>'''
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:sldSz cx="{width_emu}" cy="{height_emu}"/>
</p:presentation>'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("ppt/presentation.xml", presentation)
    return path


def test_known_canva_4x5_resolves_1080x1350(tmp_path: Path) -> None:
    source = _pptx_fixture(tmp_path / "arbitrary-name.pptx")
    resolution = resolve_pptx_native_canvas(source)

    assert resolution.source_kind == "canva"
    assert resolution.source_confidence == "reliable"
    assert resolution.uses_intended_canvas_size is True
    assert resolution.preset == CANVA_4X5_PRESET
    assert resolution.intended_canvas_size is not None
    assert resolution.intended_canvas_size.to_dict() == {"width": 1080.0, "height": 1350.0}
    assert resolution.pptx_physical_page_size is not None
    assert resolution.pptx_physical_page_size.to_dict() == {
        "width_emu": 10_287_000,
        "height_emu": 12_852_400,
        "width_pt": 810.0,
        "height_pt": 1012.0,
    }


def test_generic_office_exact_same_physical_size_is_never_forced_to_canva(tmp_path: Path) -> None:
    source = _pptx_fixture(
        tmp_path / "CANVA-looking-filename-1080x1350.pptx",
        design_id="",
        fingerprint=False,
    )
    resolution = resolve_pptx_native_canvas(source)

    assert resolution.pptx_physical_page_size is not None
    assert (resolution.pptx_physical_page_size.width_pt, resolution.pptx_physical_page_size.height_pt) == (
        810.0,
        1012.0,
    )
    assert resolution.source_kind == "office-generic"
    assert resolution.intended_canvas_size is None
    assert resolution.preset is None
    assert resolution.uses_intended_canvas_size is False


def test_design_id_without_full_origin_fingerprint_is_partial_and_not_overridden(tmp_path: Path) -> None:
    source = _pptx_fixture(tmp_path / "partial.pptx", fingerprint=False)
    resolution = resolve_pptx_native_canvas(source)

    assert resolution.source_kind == "canva"
    assert resolution.source_confidence == "partial"
    assert resolution.intended_canvas_size is None
    assert resolution.uses_intended_canvas_size is False


def test_reliable_canva_origin_with_arbitrary_physical_page_is_not_forced_to_preset(tmp_path: Path) -> None:
    source = _pptx_fixture(
        tmp_path / "other-canva-size.pptx",
        width_emu=12_192_000,
        height_emu=6_858_000,
    )
    resolution = resolve_pptx_native_canvas(source)

    assert resolution.source_kind == "canva"
    assert resolution.source_confidence == "reliable"
    assert resolution.intended_canvas_size is None
    assert resolution.preset is None
    assert resolution.uses_intended_canvas_size is False


def test_semantic_application_scales_scene_not_renderer(tmp_path: Path) -> None:
    source = _pptx_fixture(tmp_path / "known-canva.pptx")
    resolution = resolve_pptx_native_canvas(source)
    page = GraphicsPage(width=1080.0, height=1349.3333333333333)
    node = GraphicsNode(
        kind=NodeKind.RECT,
        transform=Transform(x=108.0, y=134.93333333333334, width=540.0, height=674.6666666666666),
    )
    page.add_node(node)
    document = GraphicsDocument(pages=[page])

    changed = apply_pptx_native_canvas(document, resolution)

    assert changed is True
    assert (page.width, page.height) == (1080.0, 1350.0)
    assert node.transform.x == pytest.approx(108.0)
    assert node.transform.y == pytest.approx(135.0)
    assert node.transform.width == pytest.approx(540.0)
    assert node.transform.height == pytest.approx(675.0)
    scale = _raster_scale(page, dpi=300, target_width=1229)
    assert round(page.width * scale) == 1229
    assert round(page.height * scale) == 1536


def test_generic_application_preserves_physical_aspect_ratio_scene(tmp_path: Path) -> None:
    source = _pptx_fixture(tmp_path / "generic.pptx", design_id="", fingerprint=False)
    resolution = resolve_pptx_native_canvas(source)
    physical_height = 1080.0 * (12_852_400 / 10_287_000)
    page = GraphicsPage(width=1080.0, height=physical_height)
    document = GraphicsDocument(pages=[page])

    changed = apply_pptx_native_canvas(document, resolution)

    assert changed is False
    assert page.width == 1080.0
    assert page.height == pytest.approx(physical_height)
    assert page.height != 1350.0


def test_canvas_metadata_survives_srscene_save_close_load_roundtrip(tmp_path: Path) -> None:
    source = _pptx_fixture(tmp_path / "known-canva.pptx")
    resolution = resolve_pptx_native_canvas(source)
    document = GraphicsDocument(pages=[GraphicsPage(width=1080.0, height=1349.3333333333333)])
    apply_pptx_native_canvas(document, resolution)

    expected_document = deepcopy(document.metadata["pptx_canvas"])
    expected_page = deepcopy(document.pages[0].metadata["pptx_canvas"])
    required = (
        "pptx_physical_page_size",
        "intended_canvas_size",
        "preset",
        "source",
        "source_profile",
        "origin_evidence",
    )
    before = {key: deepcopy(expected_document[key]) for key in required}

    package = save_package(document, tmp_path / "roundtrip.srscene", embed_local_assets=False)
    del document
    restored = load_package(package)

    assert restored.metadata["pptx_canvas"] == expected_document
    assert restored.pages[0].metadata["pptx_canvas"] == expected_page
    assert {key: restored.metadata["pptx_canvas"][key] for key in required} == before
    assert restored.metadata["pptx_physical_page_size"] == before["pptx_physical_page_size"]
    assert restored.metadata["intended_canvas_size"] == before["intended_canvas_size"]
    assert restored.metadata["pptx_canvas_size_preset"] == before["preset"]
    assert restored.metadata["pptx_canvas_size_source"] == before["source"]
    assert restored.metadata["pptx_canvas_size_evidence"] == before["origin_evidence"]
    assert restored.metadata["pptx_source_profile"] == before["source_profile"]
