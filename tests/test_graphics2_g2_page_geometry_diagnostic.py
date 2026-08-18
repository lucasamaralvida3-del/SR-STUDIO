from __future__ import annotations

from types import SimpleNamespace

import pytest

from srstudio.core.models import StudioProject
from srstudio.graphics2.model import CoordinateUnit, GraphicsPage
from srstudio.graphics2.qt_renderer import _raster_scale
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.reader import PptxSlide


G2_CANVA_PAGE_WIDTH_EMU = 10_287_000
G2_CANVA_PAGE_HEIGHT_EMU = 12_852_400


def _import_single_empty_slide(tmp_path, monkeypatch):
    source = tmp_path / "g2-canva-page.pptx"
    source.write_bytes(b"diagnostic-only")

    pipeline = UnifiedImportPipeline()
    slide = PptxSlide(
        index=1,
        width=G2_CANVA_PAGE_WIDTH_EMU,
        height=G2_CANVA_PAGE_HEIGHT_EMU,
        elements=[],
    )
    parsed = SimpleNamespace(slides=[slide], warnings=[])
    monkeypatch.setattr(pipeline.pptx_importer, "import_file", lambda *_args, **_kwargs: parsed)
    monkeypatch.setattr(pipeline.semantic_mapper, "map_slide", lambda _slide: [])

    project = StudioProject(name="G2 geometry diagnostic")
    pipeline._pptx(source, project)
    return project.pages[0]


def test_g2_canva_page_geometry_loses_one_pixel_before_qimage(tmp_path, monkeypatch) -> None:
    """Pin the current root cause without changing renderer/import behavior.

    The three official G2 corpus PPTX files encode 10287000 x 12852400 EMU.
    UnifiedImportPipeline normalizes every PPTX page to 1080 px width while
    preserving that exact OOXML aspect ratio. The resulting scene height is
    1349.333..., so render_png(target_width=1080) rounds to 1349. Canva's direct
    export for the measured pages is 1080 x 1350.

    This test is diagnostic: it must be updated only when the page-geometry
    contract is deliberately corrected after the official PNG baseline is frozen.
    """

    imported_page = _import_single_empty_slide(tmp_path, monkeypatch)

    assert imported_page.width == 1080.0
    assert imported_page.height == pytest.approx(1349.3333333333333)

    scene_page = GraphicsPage(
        name="diagnostic",
        width=imported_page.width,
        height=imported_page.height,
        unit=CoordinateUnit.PIXEL,
    )
    scale = _raster_scale(scene_page, dpi=300, target_width=1080)

    assert scale == pytest.approx(1.0)
    assert round(scene_page.width * scale) == 1080
    assert round(scene_page.height * scale) == 1349
    assert 1350 - round(scene_page.height * scale) == 1


def test_g2_canva_page_geometry_same_root_cause_at_quinta_reference_width(tmp_path, monkeypatch) -> None:
    imported_page = _import_single_empty_slide(tmp_path, monkeypatch)
    scene_page = GraphicsPage(
        name="diagnostic",
        width=imported_page.width,
        height=imported_page.height,
        unit=CoordinateUnit.PIXEL,
    )

    scale = _raster_scale(scene_page, dpi=300, target_width=1229)
    raw_height = scene_page.height * scale

    assert scale == pytest.approx(1229 / 1080)
    assert raw_height == pytest.approx(1535.4913580246914)
    assert round(raw_height) == 1535
    assert 1536 - round(raw_height) == 1


def test_target_width_path_does_not_depend_on_dpi() -> None:
    page = GraphicsPage(
        name="diagnostic",
        width=1080.0,
        height=1349.3333333333333,
        unit=CoordinateUnit.PIXEL,
    )

    assert _raster_scale(page, dpi=72, target_width=1080) == pytest.approx(1.0)
    assert _raster_scale(page, dpi=300, target_width=1080) == pytest.approx(1.0)
    assert _raster_scale(page, dpi=600, target_width=1080) == pytest.approx(1.0)
