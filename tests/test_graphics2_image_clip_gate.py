from __future__ import annotations

from xml.etree import ElementTree as ET

from srstudio.graphics2.import_audit import audit_import
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.pptx_structure import A_NS, PptxMappingAudit, _custom_geometry_requires_clip
from srstudio.graphics2.quality import inspect_production_gate


def _custom(path_body: str) -> ET.Element:
    return ET.fromstring(
        f'<a:custGeom xmlns:a="{A_NS}"><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>'
        f'<a:rect l="l" t="t" r="r" b="b"/><a:pathLst><a:path w="100" h="100">'
        f'{path_body}</a:path></a:pathLst></a:custGeom>'
    )


def test_rectangular_custom_geometry_does_not_create_false_mask_requirement():
    custom = _custom(
        '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
        '<a:lnTo><a:pt x="100" y="0"/></a:lnTo>'
        '<a:lnTo><a:pt x="100" y="100"/></a:lnTo>'
        '<a:lnTo><a:pt x="0" y="100"/></a:lnTo><a:close/>'
    )

    assert not _custom_geometry_requires_clip(custom)


def test_irregular_and_curved_custom_geometry_require_image_clip():
    triangle = _custom(
        '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
        '<a:lnTo><a:pt x="100" y="0"/></a:lnTo>'
        '<a:lnTo><a:pt x="20" y="100"/></a:lnTo><a:close/>'
    )
    curved = _custom(
        '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
        '<a:cubicBezTo><a:pt x="20" y="0"/><a:pt x="80" y="100"/><a:pt x="100" y="100"/></a:cubicBezTo>'
        '<a:close/>'
    )

    assert _custom_geometry_requires_clip(triangle)
    assert _custom_geometry_requires_clip(curved)


def test_production_gate_blocks_severe_irregular_image_clip_mapping_loss():
    document = GraphicsDocument(name="Canva mask loss")
    document.metadata["pptx_mapping_audit"] = PptxMappingAudit(
        source_slides=1,
        imported_pages=1,
        source_text_shapes=0,
        imported_text_nodes=0,
        source_image_shapes=10,
        imported_image_nodes=10,
        source_groups=0,
        imported_group_nodes=0,
        source_fill_rects=10,
        imported_fill_rects=10,
        source_fill_outsets=3,
        imported_fill_outsets=3,
        source_image_custom_geometry=10,
        imported_image_clips=5,
        page_count_match=True,
        text_coverage=1.0,
        image_coverage=1.0,
        group_coverage=1.0,
        fill_rect_coverage=1.0,
        fill_outset_coverage=1.0,
        image_clip_coverage=0.5,
    ).to_dict()

    audit = audit_import(document, check_local_assets=False)
    gate = inspect_production_gate(document, require_visual_fidelity=False)

    assert any(issue.code == "PPTX_IMAGE_CLIP_MAPPING_LOSS" for issue in audit.issues)
    assert any(issue.code == "PPTX_IMAGE_CLIP_COVERAGE_FAILED" for issue in gate.issues)
    assert gate.mapping_image_clip_coverage == 0.5
    assert gate.score <= 50
    assert not gate.ready
