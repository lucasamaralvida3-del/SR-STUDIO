from __future__ import annotations

"""Per-role geometry metrics for real ItemSlot corpus reconstruction.

The comparator deliberately exposes CARD, IMAGE, NAME, PRICEBLOCK, UNIT and
PRODUCT CENTER independently.  A visually large role cannot hide a bad role in
one global score, which is important when validating presets learned from real
Canva/PPTX ProductCards.
"""

from math import hypot
from typing import Any

_ROLE_FIELDS = {
    "image": "expected_image_bounds",
    "name": "expected_name_bounds",
    "priceblock": "expected_priceblock_bounds",
    "unit": "expected_unit_bounds",
    "promotion": "expected_promotion_bounds",
    "club": "expected_club_bounds",
}


def compare_slot_reconstruction(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> dict[str, Any]:
    """Compare two slot-evidence examples without collapsing role errors."""

    role_metrics = {
        role: _compare_role(expected.get(field), actual.get(field))
        for role, field in _ROLE_FIELDS.items()
    }
    return {
        "expected_example_id": str(expected.get("example_id") or ""),
        "actual_example_id": str(actual.get("example_id") or ""),
        "card_bounds": _compare_card_bounds(
            expected.get("expected_card_bounds"),
            actual.get("expected_card_bounds"),
        ),
        "product_center": _compare_product_center(expected, actual),
        "roles": role_metrics,
        "missing_expected_roles": [role for role, metric in role_metrics.items() if metric["status"] == "missing_expected"],
        "missing_actual_roles": [role for role, metric in role_metrics.items() if metric["status"] == "missing_actual"],
    }


def _compare_role(expected: Any, actual: Any) -> dict[str, Any]:
    if not isinstance(expected, dict):
        return {"status": "missing_expected"}
    if not isinstance(actual, dict):
        return {"status": "missing_actual"}
    left = expected.get("relative_bounds")
    right = actual.get("relative_bounds")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return {"status": "missing_relative_bounds"}
    return {"status": "ok", **_rect_metrics(left, right)}


def _compare_card_bounds(expected: Any, actual: Any) -> dict[str, Any]:
    if not isinstance(expected, dict):
        return {"status": "missing_expected"}
    if not isinstance(actual, dict):
        return {"status": "missing_actual"}
    keys = ("relative_page_x", "relative_page_y", "relative_page_width", "relative_page_height")
    if all(key in expected and key in actual for key in keys):
        left = {
            "x": float(expected["relative_page_x"]),
            "y": float(expected["relative_page_y"]),
            "width": float(expected["relative_page_width"]),
            "height": float(expected["relative_page_height"]),
        }
        right = {
            "x": float(actual["relative_page_x"]),
            "y": float(actual["relative_page_y"]),
            "width": float(actual["relative_page_width"]),
            "height": float(actual["relative_page_height"]),
        }
        return {"status": "ok", **_rect_metrics(left, right)}
    return {"status": "missing_page_relative_bounds"}


def _compare_product_center(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_card = expected.get("expected_card_bounds")
    actual_card = actual.get("expected_card_bounds")
    if not isinstance(expected_card, dict):
        return {"status": "missing_expected"}
    if not isinstance(actual_card, dict):
        return {"status": "missing_actual"}
    required = ("relative_page_x", "relative_page_y", "relative_page_width", "relative_page_height")
    if not all(key in expected_card and key in actual_card for key in required):
        return {"status": "missing_page_relative_bounds"}

    ex = float(expected_card["relative_page_x"]) + float(expected_card["relative_page_width"]) / 2.0
    ey = float(expected_card["relative_page_y"]) + float(expected_card["relative_page_height"]) / 2.0
    ax = float(actual_card["relative_page_x"]) + float(actual_card["relative_page_width"]) / 2.0
    ay = float(actual_card["relative_page_y"]) + float(actual_card["relative_page_height"]) / 2.0
    return {
        "status": "ok",
        "expected": {"x": ex, "y": ey},
        "actual": {"x": ax, "y": ay},
        "dx": ax - ex,
        "dy": ay - ey,
        "distance": hypot(ax - ex, ay - ey),
    }


def _rect_metrics(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
    lx = float(left.get("x") or 0.0)
    ly = float(left.get("y") or 0.0)
    lw = max(0.0, float(left.get("width") or 0.0))
    lh = max(0.0, float(left.get("height") or 0.0))
    rx = float(right.get("x") or 0.0)
    ry = float(right.get("y") or 0.0)
    rw = max(0.0, float(right.get("width") or 0.0))
    rh = max(0.0, float(right.get("height") or 0.0))

    intersection_width = max(0.0, min(lx + lw, rx + rw) - max(lx, rx))
    intersection_height = max(0.0, min(ly + lh, ry + rh) - max(ly, ry))
    intersection = intersection_width * intersection_height
    union = lw * lh + rw * rh - intersection
    iou = 1.0 if union <= 1e-12 and lw * lh <= 1e-12 and rw * rh <= 1e-12 else intersection / max(union, 1e-12)

    lcx, lcy = lx + lw / 2.0, ly + lh / 2.0
    rcx, rcy = rx + rw / 2.0, ry + rh / 2.0
    return {
        "x_error": rx - lx,
        "y_error": ry - ly,
        "width_error": rw - lw,
        "height_error": rh - lh,
        "center_distance": hypot(rcx - lcx, rcy - lcy),
        "iou": max(0.0, min(1.0, iou)),
    }
