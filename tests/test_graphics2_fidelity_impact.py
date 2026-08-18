from __future__ import annotations

import pytest

from srstudio.graphics2.fidelity_attribution import (
    FidelityAttributionReport,
    FidelityNodeSuspect,
    FidelityRegionAttribution,
)
from srstudio.graphics2.fidelity_impact import classify_fidelity_region, summarize_fidelity_impact
from srstudio.graphics2.fidelity_triage import FidelityRegion
from srstudio.graphics2.model import GraphicsNode, GraphicsPage, NodeKind, Transform


def _region(importance: float = 100.0) -> FidelityRegion:
    return FidelityRegion(
        x=0,
        y=0,
        width=100,
        height=100,
        changed_pixels=100,
        total_pixels=10000,
        changed_ratio=0.01,
        mean_error=importance / 100.0,
        max_error=40,
        importance=importance,
    )


def _suspect(node: GraphicsNode, *, score: float = 1.0, overlap: float = 0.8) -> FidelityNodeSuspect:
    return FidelityNodeSuspect(
        node_id=node.id,
        name=node.name,
        kind=node.kind.value,
        binding_role="",
        overlap_pixels=8000,
        region_overlap_ratio=overlap,
        node_overlap_ratio=0.8,
        score=score,
        z_index=node.z_index,
        rotated=False,
        diagnostic_hint="",
    )


def _attributed(node: GraphicsNode, *, importance: float = 100.0) -> FidelityRegionAttribution:
    return FidelityRegionAttribution(1, _region(importance), (_suspect(node),))


def test_fidelity_region_distinguishes_font_text_crop_mask_and_render() -> None:
    page = GraphicsPage(width=1080, height=1350)
    font = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Fonte substituída",
        transform=Transform(width=200, height=60),
        style={"font_family": "Arial", "source_font_family": "High Cruiser", "font_weight": 700},
    )
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Texto comum",
        transform=Transform(width=200, height=60),
        style={"font_family": "Arial", "source_font_family": "Arial", "font_weight": 700},
    )
    crop = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem crop",
        transform=Transform(width=200, height=200),
        style={"fill_rect": {"left": -0.2, "right": -0.2}},
    )
    mask = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem máscara",
        transform=Transform(width=200, height=200),
        metadata={"clip_path": {"paths": [{"commands": [{"op": "M", "points": [[0, 0]]}]}]}},
    )
    for node in (font, text, crop, mask):
        page.add_node(node)

    assert classify_fidelity_region(_attributed(font), page) == "FONT"
    assert classify_fidelity_region(_attributed(text), page) == "TEXT"
    assert classify_fidelity_region(_attributed(crop), page) == "CROP"
    assert classify_fidelity_region(_attributed(mask), page) == "MASK"
    assert classify_fidelity_region(FidelityRegionAttribution(1, _region(), ()), page) == "RENDER"


def test_fidelity_region_flags_visual_group_contract_before_child_kind() -> None:
    page = GraphicsPage(width=1080, height=1350)
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Grupo alpha",
        transform=Transform(width=300, height=300),
        opacity=0.5,
    )
    child = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Filho",
        parent_id=group.id,
        transform=Transform(width=200, height=60),
        style={"font_family": "Arial", "source_font_family": "Arial"},
    )
    group.children.append(child.id)
    page.add_node(group)
    page.add_node(child)

    assert classify_fidelity_region(_attributed(child), page) == "GROUP"


def test_fidelity_impact_estimates_score_gap_by_measured_region_importance() -> None:
    page = GraphicsPage(width=1080, height=1350)
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Texto",
        transform=Transform(width=200, height=60),
        style={"font_family": "Arial", "source_font_family": "Arial"},
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem",
        transform=Transform(width=200, height=200),
        style={"fit": "contain"},
    )
    page.add_node(text)
    page.add_node(image)
    regions = (
        FidelityRegionAttribution(1, _region(75.0), (_suspect(text),)),
        FidelityRegionAttribution(2, _region(25.0), (_suspect(image),)),
    )
    attribution = FidelityAttributionReport(
        page_id=page.id,
        page_name=page.name,
        page_width=page.width,
        page_height=page.height,
        image_width=1080,
        image_height=1350,
        regions=regions,
    )

    report = summarize_fidelity_impact(attribution, page, score=0.90)
    by_category = {item.category: item for item in report.categories}

    assert report.score_gap == pytest.approx(0.10)
    assert by_category["TEXT"].impact_share == pytest.approx(0.75)
    assert by_category["TEXT"].estimated_percentage_points == pytest.approx(7.5)
    assert by_category["IMAGE"].impact_share == pytest.approx(0.25)
    assert by_category["IMAGE"].estimated_percentage_points == pytest.approx(2.5)
    assert sum(item.estimated_score_loss for item in report.categories) == pytest.approx(report.score_gap)
