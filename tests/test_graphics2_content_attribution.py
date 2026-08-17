from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from srstudio.graphics2.content_attribution import build_content_attribution_report
from srstudio.graphics2.content_fidelity import compare_content_masks
from srstudio.graphics2.fidelity_attribution import attribute_fidelity_regions
from srstudio.graphics2.fidelity_triage import FidelityRegion, FidelityTriageReport
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform


def _mask(box=None):
    image = Image.new("L", (30, 30), 0)
    if box is not None:
        ImageDraw.Draw(image).rectangle(box, fill=255)
    return image


def _triage():
    regions = (
        FidelityRegion(10, 10, 20, 20, 200, 400, 0.5, 30.0, 100, 0.8),
        FidelityRegion(60, 10, 20, 20, 150, 400, 0.375, 20.0, 80, 0.6),
    )
    return FidelityTriageReport(
        width=100,
        height=100,
        pixel_tolerance=12,
        changed_pixels=350,
        total_pixels=10_000,
        changed_ratio=0.035,
        mean_error=25.0,
        max_error=100,
        bbox=(10, 10, 80, 30),
        regions=regions,
    )


def test_content_attribution_classifies_wordart_and_image_from_scene_nodes():
    document = GraphicsDocument(name="Attribution")
    page = document.active_page
    page.width = 100
    page.height = 100
    wordart = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Título WordArt",
        text="QUINTA FILÉ",
        transform=Transform(x=10, y=10, width=20, height=20),
        metadata={"pptx_wordart": True},
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=60, y=10, width=20, height=20),
    )
    page.add_node(wordart)
    page.add_node(image)

    attribution = attribute_fidelity_regions(_triage(), page)
    perfect = compare_content_masks(_mask((5, 5, 14, 14)), _mask((5, 5, 14, 14)))
    shifted = compare_content_masks(_mask((5, 5, 14, 14)), _mask((8, 5, 17, 14)))

    report = build_content_attribution_report(
        attribution,
        {1: shifted, 2: perfect},
        page=page,
    )

    assert [row.category for row in report.regions] == ["WORDART", "IMAGE"]
    assert report.regions[0].node_id == wordart.id
    assert report.regions[1].node_id == image.id
    assert 0.0 < report.summary.wordart_region_score < 100.0
    assert report.summary.image_region_score == pytest.approx(100.0)
    assert report.missing_metric_regions == ()
    assert report.orphan_metric_regions == ()
    payload = report.to_dict()
    assert payload["diagnostic_only"] is True
    assert payload["official_gate_unchanged"] is True


def test_content_attribution_reports_missing_and_orphan_region_metrics():
    document = GraphicsDocument(name="Attribution")
    page = document.active_page
    page.width = 100
    page.height = 100
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Texto",
        text="OFERTA",
        transform=Transform(x=10, y=10, width=20, height=20),
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem",
        transform=Transform(x=60, y=10, width=20, height=20),
    )
    page.add_node(text)
    page.add_node(image)

    attribution = attribute_fidelity_regions(_triage(), page)
    metric = compare_content_masks(_mask((5, 5, 14, 14)), _mask((5, 5, 14, 14)))
    report = build_content_attribution_report(attribution, {1: metric, 99: metric}, page=page)

    assert report.missing_metric_regions == (2,)
    assert report.orphan_metric_regions == (99,)
    assert len(report.regions) == 1
    assert report.regions[0].category == "TEXT"
