from __future__ import annotations

import math

import pytest
from PIL import Image, ImageDraw

from srstudio.graphics2.content_fidelity import (
    aggregate_content_scores,
    bbox_iou,
    compare_content_images,
    compare_content_masks,
    content_bbox,
    foreground_mask,
)


def _mask(box=None, *, size=(100, 80)):
    image = Image.new("L", size, 0)
    if box is not None:
        ImageDraw.Draw(image).rectangle(box, fill=255)
    return image


def test_identical_content_is_perfect_even_when_canvas_is_mostly_empty():
    reference = _mask((20, 20, 39, 39))
    metrics = compare_content_masks(reference, reference.copy())

    assert metrics.ref_bbox == (20, 20, 40, 40)
    assert metrics.render_bbox == metrics.ref_bbox
    assert metrics.bbox_iou == pytest.approx(1.0)
    assert metrics.mask_iou == pytest.approx(1.0)
    assert metrics.foreground_pixel_pass == pytest.approx(1.0)
    assert metrics.foreground_changed_area == pytest.approx(0.0)
    assert metrics.content_score == pytest.approx(100.0)


def test_empty_render_is_penalized_instead_of_being_rewarded_by_white_background():
    reference = _mask((20, 20, 39, 39))
    rendered = _mask()

    metrics = compare_content_masks(reference, rendered)

    assert metrics.ref_bbox is not None
    assert metrics.render_bbox is None
    assert metrics.mask_iou == 0.0
    assert metrics.bbox_iou == 0.0
    assert metrics.foreground_pixel_pass == 0.0
    assert metrics.foreground_changed_area == pytest.approx(1.0)
    assert metrics.content_score == 0.0
    assert math.isinf(metrics.delta_x)


def test_shifted_content_reports_position_error_and_partial_overlap():
    reference = _mask((20, 20, 39, 39))
    rendered = _mask((25, 23, 44, 42))

    metrics = compare_content_masks(reference, rendered)

    assert metrics.delta_x == pytest.approx(5.0)
    assert metrics.delta_y == pytest.approx(3.0)
    assert metrics.width_error == pytest.approx(0.0)
    assert metrics.height_error == pytest.approx(0.0)
    assert metrics.center_distance == pytest.approx(math.hypot(5, 3))
    assert 0.0 < metrics.bbox_iou < 1.0
    assert 0.0 < metrics.mask_iou < 1.0
    assert 0.0 < metrics.foreground_pixel_pass < 1.0
    assert 0.0 < metrics.content_score < 100.0


def test_foreground_mask_uses_alpha_for_isolated_attribution_regions():
    image = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((10, 8, 29, 27), fill=(255, 0, 0, 255))

    mask = foreground_mask(image)

    assert content_bbox(mask) == (10, 8, 30, 28)


def test_opaque_content_can_be_separated_from_known_background():
    reference = Image.new("RGB", (80, 50), "white")
    rendered = Image.new("RGB", (80, 50), "white")
    ImageDraw.Draw(reference).rectangle((15, 10, 34, 29), fill="black")
    ImageDraw.Draw(rendered).rectangle((17, 10, 36, 29), fill="black")

    metrics = compare_content_images(reference, rendered, background=(255, 255, 255), tolerance=2)

    assert metrics.delta_x == pytest.approx(2.0)
    assert metrics.delta_y == pytest.approx(0.0)
    assert metrics.foreground_ref_pixels == 400
    assert metrics.foreground_render_pixels == 400
    assert metrics.content_score < 100.0


def test_bbox_iou_handles_empty_regions_deterministically():
    assert bbox_iou(None, None) == 1.0
    assert bbox_iou((0, 0, 10, 10), None) == 0.0
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0


def test_aggregate_exposes_named_content_aware_diagnostics():
    perfect = compare_content_masks(_mask((10, 10, 19, 19)), _mask((10, 10, 19, 19)))
    partial = compare_content_masks(_mask((10, 10, 19, 19)), _mask((15, 10, 24, 19)))

    result = aggregate_content_scores([perfect, partial])

    assert set(result) == {
        "CONTENT_REGION_SCORE",
        "FOREGROUND_PIXEL_PASS",
        "FOREGROUND_CHANGED_AREA",
        "MASK_IOU",
        "BBOX_IOU",
    }
    assert 0.0 < result["CONTENT_REGION_SCORE"] < 100.0
    assert 0.0 < result["FOREGROUND_PIXEL_PASS"] <= 100.0
    assert result["FOREGROUND_CHANGED_AREA"] > 0.0
