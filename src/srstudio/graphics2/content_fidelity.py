from __future__ import annotations

"""Content-aware fidelity diagnostics for SR Graphics Engine 2.

These metrics intentionally complement — never replace — the official Golden
Master / Production Gate. Their purpose is to expose semantic rendering
progress that a global white-background score can hide, especially for text,
WordArt and price nodes.
"""

from dataclasses import asdict, dataclass
from math import hypot
from typing import Iterable

from PIL import Image, ImageChops

BBox = tuple[int, int, int, int]


@dataclass(slots=True, frozen=True)
class ContentRegionMetrics:
    ref_bbox: BBox | None
    render_bbox: BBox | None
    bbox_iou: float
    delta_x: float
    delta_y: float
    width_error: float
    height_error: float
    center_distance: float
    foreground_ref_pixels: int
    foreground_render_pixels: int
    foreground_intersection_pixels: int
    foreground_union_pixels: int
    foreground_pixel_pass: float
    foreground_changed_area: float
    mask_iou: float
    ink_coverage_ref: float
    ink_coverage_render: float
    ink_coverage_similarity: float
    content_score: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _binary(mask: Image.Image) -> Image.Image:
    return mask.convert("L").point(lambda value: 255 if value > 0 else 0, mode="1")


def foreground_mask(
    image: Image.Image,
    *,
    background: tuple[int, int, int] | None = None,
    tolerance: int = 8,
    alpha_threshold: int = 1,
) -> Image.Image:
    """Build a binary foreground mask from alpha or a background colour.

    If the source has meaningful transparency, alpha is authoritative. Fully
    opaque screenshots fall back to RGB distance from ``background``. When no
    background is supplied the top-left pixel is used as a deterministic local
    estimate, which is useful for isolated Attribution Lab regions.
    """

    if image.width <= 0 or image.height <= 0:
        raise ValueError("Imagem sem dimensões válidas.")
    tolerance = max(0, min(255, int(tolerance)))
    alpha_threshold = max(0, min(255, int(alpha_threshold)))

    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    extrema = alpha.getextrema()
    if extrema is not None and extrema[0] < 255:
        return alpha.point(lambda value: 255 if value >= alpha_threshold else 0, mode="1")

    rgb = rgba.convert("RGB")
    if background is None:
        background = tuple(int(value) for value in rgb.getpixel((0, 0)))
    br, bg, bb = (max(0, min(255, int(value))) for value in background)

    pixels = []
    for red, green, blue in rgb.getdata():
        distance = max(abs(red - br), abs(green - bg), abs(blue - bb))
        pixels.append(255 if distance > tolerance else 0)
    mask = Image.new("L", rgb.size)
    mask.putdata(pixels)
    return _binary(mask)


def content_bbox(mask: Image.Image) -> BBox | None:
    """Return the tight foreground bbox in Pillow's exclusive-right convention."""
    return _binary(mask).getbbox()


def bbox_iou(first: BBox | None, second: BBox | None) -> float:
    if first is None and second is None:
        return 1.0
    if first is None or second is None:
        return 0.0
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return 1.0 if union == 0 else intersection / union


def _bbox_geometry(ref_bbox: BBox | None, render_bbox: BBox | None) -> tuple[float, float, float, float, float]:
    if ref_bbox is None and render_bbox is None:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    if ref_bbox is None or render_bbox is None:
        return float("inf"), float("inf"), 1.0, 1.0, float("inf")

    ref_w = max(1, ref_bbox[2] - ref_bbox[0])
    ref_h = max(1, ref_bbox[3] - ref_bbox[1])
    render_w = max(0, render_bbox[2] - render_bbox[0])
    render_h = max(0, render_bbox[3] - render_bbox[1])
    ref_cx = (ref_bbox[0] + ref_bbox[2]) / 2.0
    ref_cy = (ref_bbox[1] + ref_bbox[3]) / 2.0
    render_cx = (render_bbox[0] + render_bbox[2]) / 2.0
    render_cy = (render_bbox[1] + render_bbox[3]) / 2.0
    dx = render_cx - ref_cx
    dy = render_cy - ref_cy
    return (
        dx,
        dy,
        abs(render_w - ref_w) / ref_w,
        abs(render_h - ref_h) / ref_h,
        hypot(dx, dy),
    )


def compare_content_masks(reference: Image.Image, rendered: Image.Image) -> ContentRegionMetrics:
    """Compare equal-sized foreground masks using content-centric metrics."""
    if reference.size != rendered.size:
        raise ValueError(f"Dimensões diferentes: referência={reference.size}, render={rendered.size}")

    ref = _binary(reference)
    out = _binary(rendered)
    ref_bbox = content_bbox(ref)
    render_bbox = content_bbox(out)
    dx, dy, width_error, height_error, center_distance = _bbox_geometry(ref_bbox, render_bbox)

    intersection = ImageChops.logical_and(ref, out)
    union = ImageChops.logical_or(ref, out)
    changed = ImageChops.logical_xor(ref, out)
    ref_pixels = _count_foreground(ref)
    out_pixels = _count_foreground(out)
    intersection_pixels = _count_foreground(intersection)
    union_pixels = _count_foreground(union)
    changed_pixels = _count_foreground(changed)
    canvas_pixels = max(1, ref.width * ref.height)

    foreground_pixel_pass = 1.0 if ref_pixels == 0 and out_pixels == 0 else (
        intersection_pixels / max(1, ref_pixels)
    )
    foreground_changed_area = 0.0 if ref_pixels == 0 and out_pixels == 0 else (
        changed_pixels / max(1, ref_pixels)
    )
    mask_iou = 1.0 if union_pixels == 0 else intersection_pixels / union_pixels
    ref_coverage = ref_pixels / canvas_pixels
    out_coverage = out_pixels / canvas_pixels
    if ref_coverage == 0 and out_coverage == 0:
        coverage_similarity = 1.0
    else:
        coverage_similarity = 1.0 - min(1.0, abs(out_coverage - ref_coverage) / max(ref_coverage, 1 / canvas_pixels))

    box_score = bbox_iou(ref_bbox, render_bbox)
    # Diagnostic score only: it must never be used to lower official thresholds.
    score = 100.0 * (
        0.35 * mask_iou
        + 0.30 * foreground_pixel_pass
        + 0.20 * box_score
        + 0.15 * coverage_similarity
    )

    return ContentRegionMetrics(
        ref_bbox=ref_bbox,
        render_bbox=render_bbox,
        bbox_iou=box_score,
        delta_x=dx,
        delta_y=dy,
        width_error=width_error,
        height_error=height_error,
        center_distance=center_distance,
        foreground_ref_pixels=ref_pixels,
        foreground_render_pixels=out_pixels,
        foreground_intersection_pixels=intersection_pixels,
        foreground_union_pixels=union_pixels,
        foreground_pixel_pass=foreground_pixel_pass,
        foreground_changed_area=foreground_changed_area,
        mask_iou=mask_iou,
        ink_coverage_ref=ref_coverage,
        ink_coverage_render=out_coverage,
        ink_coverage_similarity=coverage_similarity,
        content_score=score,
    )


def compare_content_images(
    reference: Image.Image,
    rendered: Image.Image,
    *,
    background: tuple[int, int, int] | None = None,
    tolerance: int = 8,
) -> ContentRegionMetrics:
    """Convenience wrapper that derives masks before comparing them."""
    if reference.size != rendered.size:
        raise ValueError(f"Dimensões diferentes: referência={reference.size}, render={rendered.size}")
    return compare_content_masks(
        foreground_mask(reference, background=background, tolerance=tolerance),
        foreground_mask(rendered, background=background, tolerance=tolerance),
    )


def aggregate_content_scores(metrics: Iterable[ContentRegionMetrics]) -> dict[str, float]:
    """Aggregate node/region diagnostics without inventing a Production Gate."""
    items = list(metrics)
    if not items:
        return {
            "CONTENT_REGION_SCORE": 0.0,
            "FOREGROUND_PIXEL_PASS": 0.0,
            "FOREGROUND_CHANGED_AREA": 0.0,
            "MASK_IOU": 0.0,
            "BBOX_IOU": 0.0,
        }
    count = float(len(items))
    return {
        "CONTENT_REGION_SCORE": sum(item.content_score for item in items) / count,
        "FOREGROUND_PIXEL_PASS": 100.0 * sum(item.foreground_pixel_pass for item in items) / count,
        "FOREGROUND_CHANGED_AREA": 100.0 * sum(item.foreground_changed_area for item in items) / count,
        "MASK_IOU": 100.0 * sum(item.mask_iou for item in items) / count,
        "BBOX_IOU": 100.0 * sum(item.bbox_iou for item in items) / count,
    }


def _count_foreground(mask: Image.Image) -> int:
    histogram = _binary(mask).convert("L").histogram()
    return int(histogram[255])
