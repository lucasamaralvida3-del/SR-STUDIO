from __future__ import annotations

import zipfile

import pytest

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_spacing import recover_pptx_spacing


SLIDE = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"
       xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id=\"12\" name=\"Preço principal\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:txBody>
        <a:bodyPr/><a:lstStyle/>
        <a:p>
          <a:pPr><a:lnSpc><a:spcPct val=\"125000\"/></a:lnSpc></a:pPr>
          <a:r><a:rPr spc=\"240\"/><a:t>25</a:t></a:r>
        </a:p>
      </p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

POINTS = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"
       xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id=\"14\" name=\"Texto em pontos\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:pPr><a:lnSpc><a:spcPts val=\"1312\"/></a:lnSpc></a:pPr>
        <a:r><a:rPr spc=\"-55\"/><a:t>Texto</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

MIXED = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"
       xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id=\"13\" name=\"Texto misto\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:r><a:rPr spc=\"100\"/><a:t>A</a:t></a:r>
        <a:r><a:rPr spc=\"300\"/><a:t>B</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path, xml=SLIDE):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", xml)
    return path


def _document(name="Preço principal"):
    document = GraphicsDocument(name="Spacing")
    document.active_page.add_node(
        GraphicsNode(
            id="text",
            kind=NodeKind.TEXT,
            name=name,
            transform=Transform(width=200, height=80),
            metadata={"source": "pptx", "source_name": name},
        )
    )
    return document


def test_recovers_exact_letter_and_percent_line_spacing_in_gate_and_renderer_units(tmp_path):
    document = _document()
    report = recover_pptx_spacing(_pptx(tmp_path / "spacing.pptx"), document)
    node = document.active_page.node("text")

    assert report.mapped_shapes == 1
    assert report.letter_spacing_applied == 1
    assert report.line_spacing_applied == 1
    assert report.letter_spacing_coverage == 1.0
    assert report.line_spacing_coverage == 1.0
    assert node.style["letter_spacing_pt"] == pytest.approx(2.4)
    assert node.style["letter_spacing"] == pytest.approx(3.2)
    assert node.style["line_spacing_percent"] == pytest.approx(125.0)
    assert node.metadata["pptx_spacing"]["letter_spacing_pt"] == pytest.approx(2.4)
    assert node.metadata["pptx_spacing"]["letter_spacing_px"] == pytest.approx(3.2)
    assert node.metadata["pptx_shape_id"] == "12"
    assert node.metadata["pptx_enhanced"] is True


def test_recovers_point_line_spacing_for_gate_and_qt_preview(tmp_path):
    document = _document("Texto em pontos")
    report = recover_pptx_spacing(_pptx(tmp_path / "points.pptx", POINTS), document)
    node = document.active_page.node("text")

    assert report.line_spacing_applied == 1
    assert node.style["letter_spacing_pt"] == pytest.approx(-0.55)
    assert node.style["letter_spacing"] == pytest.approx(-0.55 * 96.0 / 72.0)
    assert node.style["line_spacing_pt"] == pytest.approx(13.12)
    assert node.style["line_spacing_px"] == pytest.approx(13.12 * 96.0 / 72.0)
    assert "line_spacing_percent" not in node.style


def test_mixed_run_letter_spacing_removes_false_first_run_simplification(tmp_path):
    document = _document("Texto misto")
    node = document.active_page.node("text")
    # Simula a primeira passagem de fidelidade, que historicamente lia apenas
    # o primeiro a:rPr do shape.
    node.style["letter_spacing_pt"] = 1.0
    node.style["letter_spacing"] = 1.0 * 96.0 / 72.0

    report = recover_pptx_spacing(_pptx(tmp_path / "mixed.pptx", MIXED), document)

    assert report.letter_spacing_shapes == 1
    assert report.letter_spacing_applied == 0
    assert report.letter_spacing_coverage == 0.0
    assert any(issue.code == "PPTX_LETTER_SPACING_MIXED" for issue in report.issues)
    assert "letter_spacing" not in node.style
    assert "letter_spacing_pt" not in node.style
    assert node.metadata["pptx_spacing"]["letter_spacing_mixed"] is True


def test_does_not_guess_ambiguous_scene_names(tmp_path):
    document = _document("Preço principal")
    document.active_page.add_node(
        GraphicsNode(
            id="duplicate",
            kind=NodeKind.TEXT,
            name="Preço principal",
            transform=Transform(width=200, height=80),
            metadata={"source": "pptx", "source_name": "Preço principal"},
        )
    )

    report = recover_pptx_spacing(_pptx(tmp_path / "ambiguous.pptx"), document)

    assert report.mapped_shapes == 0
    assert report.letter_spacing_applied == 0
    assert any(issue.code == "PPTX_SPACING_SHAPE_AMBIGUOUS" for issue in report.issues)
