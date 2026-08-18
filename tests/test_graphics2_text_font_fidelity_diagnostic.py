from __future__ import annotations

from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from srstudio.graphics2 import pptx_fidelity, qt_renderer

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _text_body(*, text: str, size: int, spacing: int, line_spacing: int, second_run: str = "", second_paragraph: str = ""):
    second_run_xml = (
        f'<a:r><a:rPr lang="en-US" sz="{size}" spc="{spacing}"><a:latin typeface="Anton"/></a:rPr><a:t>{second_run}</a:t></a:r>'
        if second_run
        else ""
    )
    second_paragraph_xml = (
        f'<a:p><a:pPr algn="ctr" marL="0" indent="0"><a:lnSpc><a:spcPts val="{line_spacing}"/></a:lnSpc></a:pPr>'
        f'<a:r><a:rPr lang="en-US" sz="{size}" spc="{spacing}"><a:latin typeface="Anton"/></a:rPr><a:t>{second_paragraph}</a:t></a:r></a:p>'
        if second_paragraph
        else ""
    )
    return ET.fromstring(
        f"""
        <p:txBody xmlns:p="{P_NS}" xmlns:a="{A_NS}">
          <a:bodyPr lIns="0" tIns="0" rIns="0" bIns="0" anchor="t" rtlCol="false">
            <a:spAutoFit/>
          </a:bodyPr>
          <a:lstStyle/>
          <a:p>
            <a:pPr algn="ctr" marL="0" indent="0">
              <a:lnSpc><a:spcPts val="{line_spacing}"/></a:lnSpc>
            </a:pPr>
            <a:r>
              <a:rPr lang="en-US" sz="{size}" spc="{spacing}"><a:latin typeface="Anton"/></a:rPr>
              <a:t>{text}</a:t>
            </a:r>
            {second_run_xml}
          </a:p>
          {second_paragraph_xml}
        </p:txBody>
        """
    )


def test_frozen_anton_contract_preserves_top_anchor_zero_insets_spautofit_and_spacing():
    # Frozen-corpus signature (e.g. Quarta s9 product names): Anton, centered,
    # explicit zero text insets, top anchor, spAutoFit, negative tracking and
    # fixed DrawingML line spacing in 1/100 pt.
    body = _text_body(
        text="CREME DE AMENDOIM BOM PRINCÍPIO 250G",
        size=1742,
        spacing=-50,
        line_spacing=1881,
    )
    node = SimpleNamespace(style={}, metadata={})
    report = pptx_fidelity.PptxFidelityReport()

    pptx_fidelity._enrich_text(node, body, 1080 / 10_287_000, 1349.3333333333333 / 12_852_400, report)

    assert node.style["v_align"] == "top"
    assert node.style["align"] == "center"
    assert node.style["fit_inside_box"] is False
    assert node.style["pptx_auto_fit"] == "shape"
    # Zero insets are semantically equivalent to the renderer default and are
    # intentionally not materialized as an unnecessary style dictionary.
    assert "text_insets" not in node.style
    assert node.style["letter_spacing_pt"] == pytest.approx(-0.50)
    assert node.style["letter_spacing"] == pytest.approx(-0.50 * 96.0 / 72.0)
    assert node.style["line_spacing_pt"] == pytest.approx(18.81)
    assert node.style["line_spacing_px"] == pytest.approx(18.81 * 96.0 / 72.0)


def test_frozen_uniform_multiple_runs_are_safe_to_flatten_for_typography():
    # Real pattern from Terça s6 TextBox 80: two adjacent runs carry identical
    # Anton/size/tracking properties, so collapsing the text content does not
    # lose a rich-text style boundary in this corpus.
    body = _text_body(
        text="ALHO",
        second_run=" A GRANEL",
        size=1742,
        spacing=-50,
        line_spacing=1881,
    )
    runs = body.findall(".//{%s}r" % A_NS)

    assert len(runs) == 2
    signatures = []
    for run in runs:
        props = run.find("{%s}rPr" % A_NS)
        latin = props.find("{%s}latin" % A_NS)
        signatures.append((latin.get("typeface"), props.get("sz"), props.get("spc"), props.get("b"), props.get("i")))
    assert signatures == [("Anton", "1742", "-50", None, None)] * 2


def test_frozen_explicit_two_line_contract_is_uniform():
    # Real pattern from Quinta s14 TextBox 102: two visible paragraphs with the
    # same font, size, tracking and fixed line spacing.
    body = _text_body(
        text="LINGUIÇA TOSCANA",
        second_paragraph="PARA CHURRASCO",
        size=1224,
        spacing=-35,
        line_spacing=1321,
    )
    paragraphs = body.findall("{%s}p" % A_NS)
    assert len(paragraphs) == 2
    assert ["".join(t.text or "" for t in p.findall(".//{%s}t" % A_NS)) for p in paragraphs] == [
        "LINGUIÇA TOSCANA",
        "PARA CHURRASCO",
    ]
    assert [p.find("{%s}pPr/{%s}lnSpc/{%s}spcPts" % (A_NS, A_NS, A_NS)).get("val") for p in paragraphs] == [
        "1321",
        "1321",
    ]


def test_frozen_auto_wrap_pattern_bypasses_qpainter_explicit_line_spacing_layout():
    # Real frozen-corpus pattern: one source paragraph can be narrower than its
    # rendered glyph advance and therefore rely on automatic WordWrap. The
    # QPainter helper only takes over when node.text already contains an explicit
    # newline; with automatic wrapping it returns None and the native drawText
    # route receives no DrawingML line_spacing_px contract.
    style = {"line_spacing_px": 18.81 * 96.0 / 72.0, "nowrap": False}
    assert qt_renderer._explicit_multiline_layout(
        "CREME DE AMENDOIM BOM PRINCÍPIO 250G",
        None,
        style,
        None,
        None,
        None,
    ) is None
