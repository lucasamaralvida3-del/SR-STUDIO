from __future__ import annotations

"""Classificação e estimativa de impacto para regiões do Golden Master.

A triagem espacial mede pixels/erro e a atribuição scene-aware aponta nós
suspeitos. Este módulo combina as duas evidências em categorias operacionais do
CHAT 1 sem alterar score ou thresholds. A estimativa de perda de score reparte o
gap global proporcionalmente à importância das regiões; é um proxy de
priorização, não uma afirmação causal de quantos pontos um patch recuperará.
"""

from dataclasses import asdict, dataclass
from typing import Any

from .fidelity_attribution import FidelityAttributionReport, FidelityRegionAttribution
from .model import GraphicsNode, GraphicsPage, NodeKind

FIDELITY_CATEGORIES = (
    "FONT",
    "TEXT",
    "IMAGE",
    "CROP",
    "MASK",
    "GROUP",
    "LAYERS",
    "SHAPE",
    "RENDER",
)


@dataclass(slots=True, frozen=True)
class FidelityCategoryImpact:
    category: str
    priority: str
    regions: int
    importance: float
    impact_share: float
    estimated_score_loss: float
    estimated_percentage_points: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class FidelityImpactReport:
    score: float
    score_gap: float
    total_importance: float
    categories: tuple[FidelityCategoryImpact, ...]
    region_categories: tuple[str, ...]
    estimation: str = "score-gap-proportional-to-triage-importance"

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "score_gap": self.score_gap,
            "total_importance": self.total_importance,
            "estimation": self.estimation,
            "categories": [item.to_dict() for item in self.categories],
            "region_categories": list(self.region_categories),
        }


def summarize_fidelity_impact(
    attribution: FidelityAttributionReport,
    page: GraphicsPage,
    *,
    score: float,
) -> FidelityImpactReport:
    """Agrupa regiões por causa provável e distribui o gap visual por impacto."""

    normalized_score = max(0.0, min(1.0, float(score)))
    gap = 1.0 - normalized_score
    importance_by_category = {category: 0.0 for category in FIDELITY_CATEGORIES}
    regions_by_category = {category: 0 for category in FIDELITY_CATEGORIES}
    region_categories: list[str] = []

    for region in attribution.regions:
        category = classify_fidelity_region(region, page)
        importance = max(0.0, float(region.region.importance))
        importance_by_category[category] += importance
        regions_by_category[category] += 1
        region_categories.append(category)

    total_importance = sum(importance_by_category.values())
    category_impacts: list[FidelityCategoryImpact] = []
    for category in FIDELITY_CATEGORIES:
        importance = importance_by_category[category]
        regions = regions_by_category[category]
        if regions <= 0:
            continue
        share = importance / total_importance if total_importance > 0.0 else 0.0
        estimated_loss = gap * share
        category_impacts.append(
            FidelityCategoryImpact(
                category=category,
                priority=_priority_for_impact(share, estimated_loss),
                regions=regions,
                importance=importance,
                impact_share=share,
                estimated_score_loss=estimated_loss,
                estimated_percentage_points=estimated_loss * 100.0,
            )
        )

    category_impacts.sort(
        key=lambda item: (item.importance, item.impact_share, item.regions, item.category),
        reverse=True,
    )
    return FidelityImpactReport(
        score=normalized_score,
        score_gap=gap,
        total_importance=total_importance,
        categories=tuple(category_impacts),
        region_categories=tuple(region_categories),
    )


def classify_fidelity_region(region: FidelityRegionAttribution, page: GraphicsPage) -> str:
    """Classifica uma região usando somente sinais inequívocos da SR Scene."""

    if not region.suspects:
        return "RENDER"
    if _looks_like_layer_conflict(region):
        return "LAYERS"

    top = region.suspects[0]
    node = page.node(top.node_id)
    if node is None:
        return "RENDER"
    if _ancestor_group_has_visual_contract(page, node):
        return "GROUP"

    if node.kind == NodeKind.TEXT:
        return "FONT" if _has_font_specific_risk(node) else "TEXT"
    if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
        if node.metadata.get("clip_path"):
            return "MASK"
        style = node.style
        crop = dict(style.get("crop") or {})
        fill_rect = dict(style.get("fill_rect") or {})
        fit = str(style.get("fit") or "").lower()
        try:
            zoom = float(style.get("zoom", 1.0) or 1.0)
        except (TypeError, ValueError):
            zoom = 1.0
        if crop or fill_rect or fit == "cover" or abs(zoom - 1.0) > 1e-6:
            return "CROP"
        return "IMAGE"
    if node.kind == NodeKind.GROUP:
        return "GROUP"
    if node.kind in {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.LINE, NodeKind.PATH}:
        return "SHAPE"
    return "RENDER"


def _has_font_specific_risk(node: GraphicsNode) -> bool:
    style = node.style
    metadata = node.metadata or {}
    family = str(style.get("font_family") or "").strip().casefold()
    source_family = str(
        style.get("source_font_family") or metadata.get("source_font_name") or ""
    ).strip().casefold()
    if family and source_family and family != source_family:
        return True
    try:
        weight = int(round(float(style.get("font_weight", 400) or 400)))
    except (TypeError, ValueError):
        weight = 400
    if weight not in {400, 700}:
        return True
    if bool(metadata.get("font_substituted")) or bool(metadata.get("missing_font")):
        return True
    return False


def _looks_like_layer_conflict(region: FidelityRegionAttribution) -> bool:
    if len(region.suspects) < 2:
        return False
    first, second = region.suspects[:2]
    if first.z_index == second.z_index:
        return False
    if first.region_overlap_ratio < 0.55 or second.region_overlap_ratio < 0.55:
        return False
    strongest = max(abs(float(first.score)), 1e-9)
    return abs(float(first.score) - float(second.score)) / strongest <= 0.08


def _ancestor_group_has_visual_contract(page: GraphicsPage, node: GraphicsNode) -> bool:
    parent_id = node.parent_id
    seen: set[str] = set()
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = page.node(parent_id)
        if parent is None:
            return False
        if parent.kind == NodeKind.GROUP:
            transform = parent.transform
            if abs(float(parent.opacity) - 1.0) > 1e-9:
                return True
            if abs(float(transform.rotation)) > 1e-9:
                return True
            if abs(float(transform.scale_x) - 1.0) > 1e-9 or abs(float(transform.scale_y) - 1.0) > 1e-9:
                return True
        parent_id = parent.parent_id
    return False


def _priority_for_impact(share: float, estimated_loss: float) -> str:
    percentage_points = max(0.0, float(estimated_loss)) * 100.0
    normalized_share = max(0.0, min(1.0, float(share)))
    if percentage_points >= 2.0 or normalized_share >= 0.25:
        return "P1"
    if percentage_points >= 0.5 or normalized_share >= 0.08:
        return "P2"
    return "P3"
