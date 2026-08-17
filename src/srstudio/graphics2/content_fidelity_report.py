from __future__ import annotations

"""Named content-aware aggregates for Attribution Lab reports."""

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

from .content_fidelity import ContentRegionMetrics, aggregate_content_scores


@dataclass(slots=True, frozen=True)
class ContentAwareSummary:
    content_region_score: float
    text_region_score: float
    wordart_region_score: float
    image_region_score: float
    shape_region_score: float
    foreground_pixel_pass: float
    foreground_changed_area: float
    mask_iou: float
    bbox_iou: float
    regions: int

    def to_dict(self) -> dict[str, float | int | bool]:
        data = asdict(self)
        return {
            "CONTENT_REGION_SCORE": data["content_region_score"],
            "TEXT_REGION_SCORE": data["text_region_score"],
            "WORDART_REGION_SCORE": data["wordart_region_score"],
            "IMAGE_REGION_SCORE": data["image_region_score"],
            "SHAPE_REGION_SCORE": data["shape_region_score"],
            "FOREGROUND_PIXEL_PASS": data["foreground_pixel_pass"],
            "FOREGROUND_CHANGED_AREA": data["foreground_changed_area"],
            "MASK_IOU": data["mask_iou"],
            "BBOX_IOU": data["bbox_iou"],
            "regions": data["regions"],
            "diagnostic_only": True,
            "official_gate_unchanged": True,
        }


def summarize_content_groups(
    groups: Mapping[str, Iterable[ContentRegionMetrics]],
) -> ContentAwareSummary:
    """Aggregate Attribution Lab regions by semantic rendering category.

    Recognized categories are case-insensitive. Unknown categories still
    participate in the overall content score, which prevents silently dropping
    divergent content while keeping TEXT/WORDART explicit for prioritization.
    """

    normalized: dict[str, list[ContentRegionMetrics]] = {}
    all_metrics: list[ContentRegionMetrics] = []
    for category, values in groups.items():
        key = str(category or "OTHER").strip().upper() or "OTHER"
        items = list(values)
        normalized.setdefault(key, []).extend(items)
        all_metrics.extend(items)

    overall = aggregate_content_scores(all_metrics)

    def score(category: str) -> float:
        items = normalized.get(category, [])
        if not items:
            return 0.0
        return aggregate_content_scores(items)["CONTENT_REGION_SCORE"]

    return ContentAwareSummary(
        content_region_score=overall["CONTENT_REGION_SCORE"],
        text_region_score=score("TEXT"),
        wordart_region_score=score("WORDART"),
        image_region_score=score("IMAGE"),
        shape_region_score=score("SHAPE"),
        foreground_pixel_pass=overall["FOREGROUND_PIXEL_PASS"],
        foreground_changed_area=overall["FOREGROUND_CHANGED_AREA"],
        mask_iou=overall["MASK_IOU"],
        bbox_iou=overall["BBOX_IOU"],
        regions=len(all_metrics),
    )
