from __future__ import annotations

"""Bridge scene-aware fidelity attribution to content-aware diagnostics.

This module is diagnostic-only. It associates a region's foreground metrics
with the most likely SR Scene node and emits TEXT/WORDART/IMAGE/SHAPE buckets
used by the Alpha 35+ Attribution Lab. It never changes Golden Masters,
thresholds, renderer output or Production Gate PASS/FAIL.
"""

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .content_fidelity import ContentRegionMetrics
from .content_fidelity_report import ContentAwareSummary, summarize_content_groups
from .fidelity_attribution import FidelityAttributionReport
from .model import GraphicsNode, GraphicsPage, NodeKind


@dataclass(slots=True, frozen=True)
class ContentAttributedRegion:
    region_index: int
    category: str
    node_id: str
    node_name: str
    node_kind: str
    binding_role: str
    attribution_score: float
    content: ContentRegionMetrics

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["content"] = self.content.to_dict()
        return payload


@dataclass(slots=True, frozen=True)
class ContentAttributionReport:
    page_id: str
    regions: tuple[ContentAttributedRegion, ...]
    summary: ContentAwareSummary
    missing_metric_regions: tuple[int, ...]
    orphan_metric_regions: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "regions": [region.to_dict() for region in self.regions],
            "summary": self.summary.to_dict(),
            "missing_metric_regions": list(self.missing_metric_regions),
            "orphan_metric_regions": list(self.orphan_metric_regions),
            "diagnostic_only": True,
            "official_gate_unchanged": True,
        }


def build_content_attribution_report(
    attribution: FidelityAttributionReport,
    metrics_by_region: Mapping[int, ContentRegionMetrics],
    *,
    page: GraphicsPage | None = None,
) -> ContentAttributionReport:
    """Combine geometry attribution with per-region content metrics.

    ``metrics_by_region`` keys are 1-based ``region_index`` values from
    ``FidelityRegionAttribution``. Missing metrics are reported explicitly;
    extra metrics are retained as orphan indices instead of silently ignored.
    """

    groups: dict[str, list[ContentRegionMetrics]] = {}
    rows: list[ContentAttributedRegion] = []
    expected: set[int] = set()

    for region in attribution.regions:
        index = int(region.region_index)
        expected.add(index)
        metrics = metrics_by_region.get(index)
        if metrics is None:
            continue

        suspect = region.suspects[0] if region.suspects else None
        node = page.node(suspect.node_id) if page is not None and suspect is not None else None
        category = _category_for_suspect(
            suspect_kind=str(suspect.kind if suspect is not None else ""),
            node=node,
        )
        groups.setdefault(category, []).append(metrics)
        rows.append(
            ContentAttributedRegion(
                region_index=index,
                category=category,
                node_id=str(suspect.node_id if suspect is not None else ""),
                node_name=str(suspect.name if suspect is not None else ""),
                node_kind=str(suspect.kind if suspect is not None else ""),
                binding_role=str(suspect.binding_role if suspect is not None else ""),
                attribution_score=float(suspect.score if suspect is not None else 0.0),
                content=metrics,
            )
        )

    provided = {int(index) for index in metrics_by_region}
    missing = tuple(sorted(expected - provided))
    orphan = tuple(sorted(provided - expected))
    return ContentAttributionReport(
        page_id=attribution.page_id,
        regions=tuple(rows),
        summary=summarize_content_groups(groups),
        missing_metric_regions=missing,
        orphan_metric_regions=orphan,
    )


def _category_for_suspect(*, suspect_kind: str, node: GraphicsNode | None) -> str:
    kind = str(suspect_kind or "").strip().lower()
    if node is not None:
        kind = str(getattr(node.kind, "value", node.kind) or kind).strip().lower()

    if kind == NodeKind.TEXT.value:
        return "WORDART" if _looks_like_wordart(node) else "TEXT"
    if kind in {NodeKind.IMAGE.value, NodeKind.BACKGROUND.value}:
        return "IMAGE"
    if kind in {
        NodeKind.RECT.value,
        NodeKind.ELLIPSE.value,
        NodeKind.LINE.value,
        NodeKind.PATH.value,
    }:
        return "SHAPE"
    return "OTHER"


def _looks_like_wordart(node: GraphicsNode | None) -> bool:
    if node is None:
        return False

    # Importers have evolved across Alphas, so classification intentionally
    # accepts a small stable family of explicit metadata/style markers rather
    # than coupling the lab to one historical key spelling.
    sources = (node.metadata or {}, node.style or {})
    truthy_keys = {
        "wordart",
        "is_wordart",
        "pptx_wordart",
        "source_wordart",
        "text_warped",
    }
    value_keys = {
        "text_warp",
        "preset_text_warp",
        "prst_tx_warp",
        "prsttxwarp",
        "source_text_kind",
        "text_effect_kind",
    }
    for source in sources:
        for key in truthy_keys:
            if _truthy(source.get(key)):
                return True
        for key in value_keys:
            value = str(source.get(key) or "").strip().casefold()
            if value and value not in {"none", "false", "0", "normal", "plain"}:
                return True
            if "wordart" in value or "word art" in value:
                return True
    return False


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().casefold() in {"1", "true", "yes", "sim", "wordart", "word art"}
