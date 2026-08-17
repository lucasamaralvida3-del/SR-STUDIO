from __future__ import annotations

from zipfile import ZipFile

from srstudio.graphics2.import_audit import audit_import
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_structure import PptxMappingAudit, PptxStructureReport, inspect_pptx_structure
from srstudio.graphics2.quality import inspect_production_gate


PRESENTATION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldSz cx="9144000" cy="11430000"/>
</p:presentation>
"""


def _text_shape(
    shape_id: int,
    name: str,
    text: str,
    *,
    image_fill: bool = False,
    custom: bool = False,
    fill_rect_attrs: str = "",
    autofit: str = "",
) -> str:
    fill_rect = f"<a:fillRect {fill_rect_attrs}/>" if fill_rect_attrs else "<a:fillRect/>"
    fill = (
        '<a:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        f'r:embed="rId{shape_id}"/><a:stretch>{fill_rect}</a:stretch></a:blipFill>'
        if image_fill
        else ""
    )
    geometry = (
        '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/>'
        '<a:pathLst><a:path w="100" h="100"><a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
        '<a:lnTo><a:pt x="100" y="0"/></a:lnTo><a:lnTo><a:pt x="100" y="100"/></a:lnTo>'
        '<a:close/></a:path></a:pathLst></a:custGeom>'
        if custom
        else '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
    )
    autofit_xml = {
        "shape": "<a:spAutoFit/>",
        "normal": '<a:normAutofit fontScale="92000" lnSpcReduction="20000"/>',
        "none": "<a:noAutofit/>",
    }.get(autofit, "")
    return f"""
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>{fill}{geometry}</p:spPr>
      <p:txBody><a:bodyPr>{autofit_xml}</a:bodyPr><a:lstStyle/><a:p><a:r><a:rPr lang="pt-BR"/><a:t>{text}</a:t></a:r></a:p></p:txBody>
    </p:sp>
    """


def _slide_xml() -> str:
    shapes = [
        _text_shape(2, "Currency", "R$", autofit="shape"),
        _text_shape(3, "Whole", "25", autofit="shape"),
        _text_shape(4, "Cents", ",77", autofit="normal"),
        _text_shape(5, "Unit", "KG", autofit="none"),
        _text_shape(6, "Name", "LINGUIÇA MISTA CASEIRA SR"),
        _text_shape(
            7,
            "Canva Image Fill",
            "",
            image_fill=True,
            custom=True,
            fill_rect_attrs='l="-30959" t="0" r="-30437" b="0"',
        ),
    ]
    group = """
      <p:grpSp>
        <p:nvGrpSpPr><p:cNvPr id="20" name="Group 20"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
        <p:grpSpPr/>
        <p:sp>
          <p:nvSpPr><p:cNvPr id="21" name="Grouped Shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
          <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>GRUPO</a:t></a:r></a:p></p:txBody>
        </p:sp>
      </p:grpSp>
    """
    picture = """
      <p:pic>
        <p:nvPicPr><p:cNvPr id="30" name="Picture 1"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="rId30"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    """
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <p:cSld><p:spTree>{''.join(shapes)}{group}{picture}</p:spTree></p:cSld>
    </p:sld>
    """


def _write_pptx(path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION_XML)
        archive.writestr("ppt/slides/slide1.xml", _slide_xml())


def test_structure_scanner_counts_canva_image_fills_split_prices_groups_and_autofit(tmp_path):
    source = tmp_path / "canva-structure.pptx"
    _write_pptx(source)

    report = inspect_pptx_structure(source)

    assert report.ready
    assert report.slide_count == 1
    assert report.slide_width_emu == 9144000
    assert report.slide_height_emu == 11430000
    assert report.text_shapes == 6
    assert report.shape_autofit == 2
    assert report.normal_autofit == 1
    assert report.no_autofit == 1
    assert report.autofit_contracts == 4
    assert report.pictures == 1
    assert report.image_fill_shapes == 1
    assert report.image_fill_rects == 2
    assert report.image_fill_outsets == 1
    assert report.groups == 1
    assert report.custom_geometry == 1
    assert report.image_custom_geometry == 1
    assert report.estimated_split_prices == 1
    slide = report.slides[0]
    assert slide.image_fill_shape_names == ["Canva Image Fill"]
    assert (slide.shape_autofit, slide.normal_autofit, slide.no_autofit, slide.autofit_contracts) == (2, 1, 1, 4)
    assert slide.image_fill_rects == 2
    assert slide.image_fill_outsets == 1
    assert slide.image_custom_geometry == 1
    assert (slide.currency_tokens, slide.integer_tokens, slide.cents_tokens, slide.unit_tokens) == (1, 1, 1, 1)


def test_mapping_audit_treats_autofit_type_as_semantic_visual_contract():
    report = PptxStructureReport(
        slide_count=1,
        text_shapes=10,
        shape_autofit=4,
        normal_autofit=1,
        pictures=1,
        image_fill_shapes=3,
        image_fill_rects=4,
        image_fill_outsets=2,
        groups=4,
    )
    document = GraphicsDocument()
    page = document.active_page
    for index in range(9):
        style = {"font_family": "Arial"}
        if index < 2:
            style["pptx_auto_fit"] = "shape"
        elif index == 2:
            style["pptx_auto_fit"] = "normal"
        elif index in {3, 4}:
            # A quantidade total de contratos bate em 5, mas dois shape-auto-fit
            # foram semanticamente trocados por normAutofit.
            style["pptx_auto_fit"] = "normal"
        page.add_node(
            GraphicsNode(
                kind=NodeKind.TEXT,
                text=f"Texto {index}",
                transform=Transform(x=10, y=10 + index * 20, width=100, height=18),
                style=style,
            )
        )
    page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            transform=Transform(x=200, y=200, width=80, height=80),
            style={"fill_rect": {"l": -0.2, "t": 0, "r": -0.1, "b": 0}},
            metadata={"bound_image_source": "https://example.invalid/image.png"},
        )
    )
    page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            transform=Transform(x=300, y=200, width=80, height=80),
            style={"fill_rect": {"l": 0, "t": 0, "r": 0, "b": 0}},
            metadata={"bound_image_source": "https://example.invalid/image.png"},
        )
    )
    page.add_node(GraphicsNode(kind=NodeKind.GROUP, transform=Transform(width=100, height=100)))

    mapping = report.audit_document(document)

    assert mapping.page_count_match
    assert mapping.text_coverage == 0.9
    assert mapping.source_autofit_contracts == 5
    assert mapping.imported_autofit_contracts == 5
    assert mapping.shape_autofit_coverage == 0.5
    assert mapping.normal_autofit_coverage == 1.0
    assert mapping.autofit_coverage == 0.5
    assert mapping.image_coverage == 0.5
    assert mapping.group_coverage == 0.25
    assert mapping.fill_rect_coverage == 0.5
    assert mapping.fill_outset_coverage == 0.5
    assert any("auto-fit PPTX" in warning for warning in mapping.warnings)
    assert any("p:sp/a:blipFill" in warning for warning in mapping.warnings)
    assert any("stretch/fillRect" in warning for warning in mapping.warnings)
    assert any("outset negativo" in warning for warning in mapping.warnings)


def test_production_gate_blocks_severe_pptx_autofit_semantic_loss():
    document = GraphicsDocument(name="PPTX mapping loss")
    document.metadata["pptx_mapping_audit"] = PptxMappingAudit(
        source_slides=1,
        imported_pages=1,
        source_text_shapes=10,
        imported_text_nodes=10,
        source_autofit_contracts=10,
        imported_autofit_contracts=10,
        source_shape_autofit=10,
        imported_shape_autofit=5,
        source_normal_autofit=0,
        imported_normal_autofit=5,
        page_count_match=True,
        text_coverage=1.0,
        autofit_coverage=0.5,
        shape_autofit_coverage=0.5,
        normal_autofit_coverage=1.0,
    ).to_dict()

    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert not gate.ready
    assert gate.mapping_autofit_coverage == 0.5
    assert gate.score <= 50
    assert any(issue.code == "PPTX_AUTOFIT_COVERAGE_FAILED" for issue in gate.issues)


def test_import_audit_and_production_gate_block_severe_pptx_mapping_loss():
    document = GraphicsDocument(name="PPTX mapping loss")
    document.metadata["pptx_mapping_audit"] = PptxMappingAudit(
        source_slides=1,
        imported_pages=1,
        source_text_shapes=10,
        imported_text_nodes=6,
        source_autofit_contracts=10,
        imported_autofit_contracts=5,
        source_shape_autofit=10,
        imported_shape_autofit=5,
        source_image_shapes=10,
        imported_image_nodes=4,
        source_groups=4,
        imported_group_nodes=1,
        source_fill_rects=10,
        imported_fill_rects=5,
        source_fill_outsets=5,
        imported_fill_outsets=2,
        page_count_match=True,
        text_coverage=0.6,
        autofit_coverage=0.5,
        shape_autofit_coverage=0.5,
        image_coverage=0.4,
        group_coverage=0.25,
        fill_rect_coverage=0.5,
        fill_outset_coverage=0.4,
    ).to_dict()

    audit = audit_import(document, check_local_assets=False)
    gate = inspect_production_gate(document, require_visual_fidelity=False)

    codes = {issue.code for issue in audit.issues}
    assert "PPTX_TEXT_MAPPING_LOSS" in codes
    assert "PPTX_IMAGE_MAPPING_LOSS" in codes
    assert "PPTX_GROUP_MAPPING_RISK" in codes
    assert "PPTX_FILL_RECT_MAPPING_LOSS" in codes
    assert "PPTX_FILL_OUTSET_MAPPING_LOSS" in codes
    assert audit.errors >= 4
    assert not gate.ready
    assert gate.mapping_text_coverage == 0.6
    assert gate.mapping_autofit_coverage == 0.5
    assert gate.mapping_image_coverage == 0.4
    assert gate.mapping_group_coverage == 0.25
    assert gate.mapping_fill_rect_coverage == 0.5
    assert gate.mapping_fill_outset_coverage == 0.4
    assert gate.score <= 40
    assert any(issue.code == "PPTX_AUTOFIT_COVERAGE_FAILED" for issue in gate.issues)
    assert any(issue.code == "PPTX_IMAGE_COVERAGE_FAILED" for issue in gate.issues)
    assert any(issue.code == "PPTX_FILL_RECT_COVERAGE_FAILED" for issue in gate.issues)
    assert any(issue.code == "PPTX_FILL_OUTSET_COVERAGE_FAILED" for issue in gate.issues)


def test_production_gate_accepts_complete_mapping_metadata():
    document = GraphicsDocument(name="PPTX mapping complete")
    document.metadata["graphics2_import_audit"] = {"confidence": 1.0, "errors": 0, "warnings": 0}
    document.metadata["pptx_mapping_audit"] = PptxMappingAudit(
        source_slides=1,
        imported_pages=1,
        source_text_shapes=12,
        imported_text_nodes=12,
        source_autofit_contracts=8,
        imported_autofit_contracts=8,
        source_shape_autofit=8,
        imported_shape_autofit=8,
        source_image_shapes=8,
        imported_image_nodes=8,
        source_groups=2,
        imported_group_nodes=2,
        source_fill_rects=8,
        imported_fill_rects=8,
        source_fill_outsets=3,
        imported_fill_outsets=3,
        page_count_match=True,
        text_coverage=1.0,
        autofit_coverage=1.0,
        shape_autofit_coverage=1.0,
        image_coverage=1.0,
        group_coverage=1.0,
        fill_rect_coverage=1.0,
        fill_outset_coverage=1.0,
    ).to_dict()

    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert gate.mapping_page_count_match is True
    assert gate.mapping_text_coverage == 1.0
    assert gate.mapping_autofit_coverage == 1.0
    assert gate.mapping_image_coverage == 1.0
    assert gate.mapping_group_coverage == 1.0
    assert gate.mapping_fill_rect_coverage == 1.0
    assert gate.mapping_fill_outset_coverage == 1.0
    assert not any(issue.code.startswith("PPTX_") and "COVERAGE" in issue.code for issue in gate.issues)
