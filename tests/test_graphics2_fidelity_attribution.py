from __future__ import annotations

import pytest

from srstudio.graphics2.fidelity_attribution import attribute_fidelity_regions
from srstudio.graphics2.fidelity_triage import FidelityRegion, FidelityTriageReport
from srstudio.graphics2.model import BindingRole, GraphicsNode, GraphicsPage, NodeKind, Transform


def _report(*regions: FidelityRegion, width: int = 2000, height: int = 2000) -> FidelityTriageReport:
    changed = sum(region.changed_pixels for region in regions)
    return FidelityTriageReport(
        width=width,
        height=height,
        pixel_tolerance=12,
        changed_pixels=changed,
        total_pixels=width * height,
        changed_ratio=changed / (width * height),
        mean_error=20.0 if regions else 0.0,
        max_error=80 if regions else 0,
        bbox=None,
        regions=regions,
    )


def _region(x: int, y: int, width: int, height: int) -> FidelityRegion:
    area = width * height
    return FidelityRegion(
        x=x,
        y=y,
        width=width,
        height=height,
        changed_pixels=max(1, area // 2),
        total_pixels=area,
        changed_ratio=0.5,
        mean_error=25.0,
        max_error=90,
        importance=float(area) * 12.5,
    )


def test_attributes_region_to_semantic_price_node_before_background() -> None:
    page = GraphicsPage(id="page_1", name="Quinta Filé", width=1000, height=1000)
    page.add_node(
        GraphicsNode(
            id="background",
            kind=NodeKind.BACKGROUND,
            name="Fundo",
            transform=Transform(x=0, y=0, width=1000, height=1000),
            z_index=0,
        )
    )
    page.add_node(
        GraphicsNode(
            id="price_reais",
            kind=NodeKind.TEXT,
            name="Preço reais",
            transform=Transform(x=120, y=120, width=120, height=90),
            binding_role=BindingRole.PRICE_REAIS,
            z_index=20,
        )
    )

    report = _report(_region(200, 200, 400, 400))
    attribution = attribute_fidelity_regions(report, page)

    assert attribution.unmatched_regions == 0
    suspects = attribution.regions[0].suspects
    assert suspects[0].node_id == "price_reais"
    assert suspects[0].binding_role == "price_reais"
    assert suspects[0].diagnostic_hint.startswith("preço:")
    assert any(item.node_id == "background" for item in suspects)


def test_rotated_node_uses_transformed_aabb() -> None:
    page = GraphicsPage(id="page_1", width=1000, height=1000)
    page.add_node(
        GraphicsNode(
            id="rotated_text",
            kind=NodeKind.TEXT,
            name="Rotacionado",
            transform=Transform(x=400, y=400, width=200, height=40, rotation=45),
            z_index=5,
        )
    )

    report = _report(_region(760, 720, 480, 480))
    attribution = attribute_fidelity_regions(report, page)

    suspect = attribution.regions[0].suspects[0]
    assert suspect.node_id == "rotated_text"
    assert suspect.rotated is True
    assert suspect.overlap_pixels > 0


def test_ignores_hidden_and_non_overlapping_nodes_and_validates_page_size() -> None:
    page = GraphicsPage(id="page_1", width=1000, height=1000)
    page.add_node(
        GraphicsNode(
            id="hidden",
            kind=NodeKind.TEXT,
            visible=False,
            transform=Transform(x=100, y=100, width=200, height=200),
        )
    )
    page.add_node(
        GraphicsNode(
            id="far",
            kind=NodeKind.IMAGE,
            transform=Transform(x=800, y=800, width=100, height=100),
        )
    )

    report = _report(_region(200, 200, 200, 200))
    attribution = attribute_fidelity_regions(report, page)
    assert attribution.unmatched_regions == 1
    assert attribution.regions[0].suspects == ()

    invalid = GraphicsPage(id="bad", width=0, height=1000)
    with pytest.raises(ValueError, match="largura e altura positivas"):
        attribute_fidelity_regions(report, invalid)
