from __future__ import annotations

from zipfile import ZipFile

import pytest

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_structure import inspect_pptx_structure
from srstudio.graphics2.quality import inspect_production_gate


PRESENTATION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="9144000" cy="11430000"/>
</p:presentation>
"""


def _shape(shape_id: int, name: str, *, letter_hundredths: int, line_tag: str, line_value: int) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      <p:txBody>
        <a:bodyPr><a:spAutoFit/></a:bodyPr><a:lstStyle/>
        <a:p>
          <a:pPr><a:lnSpc><a:{line_tag} val="{line_value}"/></a:lnSpc></a:pPr>
          <a:r><a:rPr lang="pt-BR" spc="{letter_hundredths}"/><a:t>{name}</a:t></a:r>
        </a:p>
      </p:txBody>
    </p:sp>
    """


def _slide_xml() -> str:
    shapes = [
        _shape(2, "Texto 1", letter_hundredths=-55, line_tag="spcPts", line_value=1312),
        _shape(3, "Texto 2", letter_hundredths=-103, line_tag="spcPts", line_value=1603),
        _shape(4, "Texto 3", letter_hundredths=-36, line_tag="spcPts", line_value=3840),
        _shape(5, "Texto 4", letter_hundredths=-57, line_tag="spcPts", line_value=1357),
        _shape(6, "Texto 5", letter_hundredths=-330, line_tag="spcPct", line_value=100000),
    ]
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:cSld><p:spTree>{''.join(shapes)}</p:spTree></p:cSld>
    </p:sld>
    """


def _write_pptx(path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION_XML)
        archive.writestr("ppt/slides/slide1.xml", _slide_xml())


def _document_from_report(report, *, corrupt_indices: set[int] | None = None) -> GraphicsDocument:
    corrupt_indices = set(corrupt_indices or set())
    document = GraphicsDocument(name="PPTX spacing coverage")
    page = document.active_page
    by_name_letter = {item["shape_name"]: item for item in report.letter_spacing_contracts}
    by_name_line = {item["shape_name"]: item for item in report.line_spacing_contracts}
    for index, name in enumerate(sorted(by_name_letter), start=1):
        letter = by_name_letter[name]
        line = by_name_line[name]
        style = {
            "font_family": "Arial",
            "pptx_auto_fit": "shape",
            "letter_spacing_pt": float(letter["value"]),
        }
        if line["unit"] == "pt":
            style["line_spacing_pt"] = float(line["value"])
            style["line_spacing_px"] = float(line["value"]) * 96.0 / 72.0
        else:
            style["line_spacing_percent"] = float(line["value"])
        if index in corrupt_indices:
            style["letter_spacing_pt"] += 0.25
            if line["unit"] == "pt":
                style["line_spacing_pt"] += 0.25
            else:
                style["line_spacing_percent"] += 1.0
        page.add_node(
            GraphicsNode(
                kind=NodeKind.TEXT,
                name=name,
                text=name,
                transform=Transform(x=10, y=index * 40, width=220, height=30),
                style=style,
                metadata={"source_name": name},
            )
        )
    return document


def test_structure_scanner_records_exact_letter_and_line_spacing_values(tmp_path):
    source = tmp_path / "spacing.pptx"
    _write_pptx(source)

    report = inspect_pptx_structure(source)

    assert report.ready
    assert report.text_shapes == 5
    assert report.letter_spacing_count == 5
    assert report.line_spacing_count == 5
    assert report.slides[0].letter_spacing_count == 5
    assert report.slides[0].line_spacing_count == 5
    assert report.letter_spacing_contracts[0]["value"] == pytest.approx(-0.55)
    assert report.line_spacing_contracts[0] == {
        "slide": 1,
        "shape_name": "Texto 1",
        "unit": "pt",
        "value": pytest.approx(13.12),
    }
    percent = next(item for item in report.line_spacing_contracts if item["shape_name"] == "Texto 5")
    assert percent["unit"] == "percent"
    assert percent["value"] == pytest.approx(100.0)


def test_spacing_mapping_requires_matching_source_shape_and_exact_value(tmp_path):
    source = tmp_path / "spacing.pptx"
    _write_pptx(source)
    report = inspect_pptx_structure(source)

    complete = report.audit_document(_document_from_report(report))
    assert complete.source_letter_spacing_contracts == 5
    assert complete.imported_letter_spacing_contracts == 5
    assert complete.letter_spacing_coverage == 1.0
    assert complete.source_line_spacing_contracts == 5
    assert complete.imported_line_spacing_contracts == 5
    assert complete.line_spacing_coverage == 1.0

    damaged = report.audit_document(_document_from_report(report, corrupt_indices={1, 2}))
    assert damaged.imported_letter_spacing_contracts == 3
    assert damaged.imported_line_spacing_contracts == 3
    assert damaged.letter_spacing_coverage == pytest.approx(0.6)
    assert damaged.line_spacing_coverage == pytest.approx(0.6)
    assert any("letter spacing PPTX" in warning for warning in damaged.warnings)
    assert any("line spacing PPTX" in warning for warning in damaged.warnings)


def test_production_gate_blocks_severe_exact_spacing_loss(tmp_path):
    source = tmp_path / "spacing.pptx"
    _write_pptx(source)
    report = inspect_pptx_structure(source)
    document = _document_from_report(report, corrupt_indices={1, 2})
    mapping = report.audit_document(document)
    document.metadata["pptx_mapping_audit"] = mapping.to_dict()

    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert not gate.ready
    assert gate.mapping_letter_spacing_coverage == pytest.approx(0.6)
    assert gate.mapping_line_spacing_coverage == pytest.approx(0.6)
    assert gate.score <= 60
    codes = {issue.code for issue in gate.issues}
    assert "PPTX_LETTER_SPACING_COVERAGE_FAILED" in codes
    assert "PPTX_LINE_SPACING_COVERAGE_FAILED" in codes


def test_production_gate_warns_between_80_and_95_percent(tmp_path):
    source = tmp_path / "spacing.pptx"
    _write_pptx(source)
    report = inspect_pptx_structure(source)

    # Use ten contracts so one damaged shape produces 90% coverage.
    report.letter_spacing_contracts *= 2
    report.line_spacing_contracts *= 2
    document = _document_from_report(report, corrupt_indices={1})
    # Duplicate source contracts map to the same source shape; one damaged shape
    # therefore removes both copies and yields 8/10 = 80%. Use one additional
    # exact synthetic contract to land inside the warning band at 90%.
    report.letter_spacing_contracts = report.letter_spacing_contracts[:9]
    report.line_spacing_contracts = report.line_spacing_contracts[:9]
    mapping = report.audit_document(document)
    document.metadata["pptx_mapping_audit"] = mapping.to_dict()

    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert 0.80 <= gate.mapping_letter_spacing_coverage < 0.95
    assert 0.80 <= gate.mapping_line_spacing_coverage < 0.95
    codes = {issue.code for issue in gate.issues}
    assert "PPTX_LETTER_SPACING_COVERAGE_LOW" in codes
    assert "PPTX_LINE_SPACING_COVERAGE_LOW" in codes
