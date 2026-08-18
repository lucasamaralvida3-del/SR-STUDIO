from __future__ import annotations

import io
import zipfile

import pytest

from srstudio.core.models import StudioProject
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.canvas_size import EMU_PER_POINT, resolve_canvas_size
from srstudio.importers.pptx.reader import PptxImportResult, PptxSlide


def _package(application: str) -> zipfile.ZipFile:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(
            "docProps/app.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                f"<Application>{application}</Application>"
                "</Properties>"
            ),
        )
    payload.seek(0)
    return zipfile.ZipFile(payload)


def test_canva_4_5_resolves_exact_1080x1350_from_independent_source_signature():
    with _package("Canva") as package:
        result = resolve_canvas_size(
            package,
            int(810 * EMU_PER_POINT),
            int(1012 * EMU_PER_POINT),
        )

    assert result.source_kind == "canva"
    assert result.pptx_physical_page_size["width_pt"] == pytest.approx(810.0)
    assert result.pptx_physical_page_size["height_pt"] == pytest.approx(1012.0)
    assert result.intended_canvas_size == {"width": 1080, "height": 1350}
    assert result.uses_intended_canvas_size is True
    assert result.preset == "canva-4:5-1080x1350"


def test_generic_pptx_with_same_physical_dimensions_does_not_get_canva_override():
    with _package("Microsoft PowerPoint") as package:
        result = resolve_canvas_size(
            package,
            int(810 * EMU_PER_POINT),
            int(1012 * EMU_PER_POINT),
        )

    assert result.source_kind == "office-generic"
    assert result.intended_canvas_size is None
    assert result.uses_intended_canvas_size is False


def test_non_canva_office_document_keeps_physical_aspect_ratio_in_pipeline(tmp_path, monkeypatch):
    source = tmp_path / "office-generic.pptx"
    source.write_bytes(b"synthetic")
    width = int(10 * 72 * EMU_PER_POINT)
    height = int(7.5 * 72 * EMU_PER_POINT)
    parsed = PptxImportResult(
        slides=[PptxSlide(index=1, width=width, height=height)],
        metadata={
            "pptx_physical_page_size": {
                "width_emu": width,
                "height_emu": height,
                "width_pt": 720.0,
                "height_pt": 540.0,
            },
            "intended_canvas_size": None,
            "source_kind": "office-generic",
            "source_evidence": [],
            "preset": None,
            "uses_intended_canvas_size": False,
        },
    )
    pipeline = UnifiedImportPipeline()
    monkeypatch.setattr(pipeline.pptx_importer, "import_file", lambda *_args, **_kwargs: parsed)

    project = StudioProject()
    pipeline.import_file(source, project)

    page = project.pages[0]
    assert page.width == pytest.approx(1080.0)
    assert page.height == pytest.approx(810.0)
    assert page.height / page.width == pytest.approx(height / width)
    assert project.settings["pptx_physical_page_size"]["width_pt"] == pytest.approx(720.0)
    assert project.settings["intended_canvas_size"] is None


def test_canva_pipeline_uses_exact_intended_canvas_and_preserves_physical_size(tmp_path, monkeypatch):
    source = tmp_path / "canva-export.pptx"
    source.write_bytes(b"synthetic")
    width = int(810 * EMU_PER_POINT)
    height = int(1012 * EMU_PER_POINT)
    parsed = PptxImportResult(
        slides=[PptxSlide(index=1, width=width, height=height)],
        metadata={
            "pptx_physical_page_size": {
                "width_emu": width,
                "height_emu": height,
                "width_pt": 810.0,
                "height_pt": 1012.0,
            },
            "intended_canvas_size": {"width": 1080, "height": 1350},
            "source_kind": "canva",
            "source_evidence": ["docProps/app.xml"],
            "preset": "canva-4:5-1080x1350",
            "uses_intended_canvas_size": True,
        },
    )
    pipeline = UnifiedImportPipeline()
    monkeypatch.setattr(pipeline.pptx_importer, "import_file", lambda *_args, **_kwargs: parsed)

    project = StudioProject()
    pipeline.import_file(source, project)

    page = project.pages[0]
    assert (page.width, page.height) == (1080.0, 1350.0)
    assert project.settings["pptx_physical_page_size"]["height_pt"] == pytest.approx(1012.0)
    assert project.settings["intended_canvas_size"] == {"width": 1080, "height": 1350}
    assert project.settings["pptx_canvas_size_source"] == "canva"
    assert project.settings["pptx_canvas_size_preset"] == "canva-4:5-1080x1350"
