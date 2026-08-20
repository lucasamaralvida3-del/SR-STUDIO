from __future__ import annotations

from copy import deepcopy

import pytest

from srstudio.graphics2.slot_corpus_reconstruction import compare_slot_reconstruction


def _role(x: float, y: float, width: float, height: float) -> dict:
    return {
        "node_ids": ["node"],
        "bounds": {"x": x * 100, "y": y * 100, "width": width * 100, "height": height * 100},
        "relative_bounds": {"x": x, "y": y, "width": width, "height": height},
    }


def _example() -> dict:
    return {
        "example_id": "page-1:slot-a",
        "expected_card_bounds": {
            "x": 100,
            "y": 200,
            "width": 300,
            "height": 400,
            "relative_page_x": 0.10,
            "relative_page_y": 0.20,
            "relative_page_width": 0.30,
            "relative_page_height": 0.40,
        },
        "expected_product_center": {"x": 250, "y": 400, "relative_x": 0.5, "relative_y": 0.5},
        "expected_image_bounds": _role(0.08, 0.16, 0.72, 0.48),
        "expected_name_bounds": _role(0.08, 0.04, 0.84, 0.10),
        "expected_priceblock_bounds": _role(0.10, 0.69, 0.68, 0.22),
        "expected_unit_bounds": _role(0.78, 0.77, 0.18, 0.11),
        "expected_promotion_bounds": None,
        "expected_club_bounds": None,
    }


def test_exact_reconstruction_reports_each_role_independently() -> None:
    expected = _example()
    actual = deepcopy(expected)
    actual["example_id"] = "page-1:slot-rebuilt"

    result = compare_slot_reconstruction(expected, actual)

    assert result["card_bounds"]["iou"] == pytest.approx(1.0)
    assert result["product_center"]["distance"] == pytest.approx(0.0)
    for role in ("image", "name", "priceblock", "unit"):
        assert result["roles"][role]["status"] == "ok"
        assert result["roles"][role]["iou"] == pytest.approx(1.0)
        assert result["roles"][role]["center_distance"] == pytest.approx(0.0)
    assert result["roles"]["promotion"]["status"] == "missing_expected"
    assert result["roles"]["club"]["status"] == "missing_expected"


def test_name_error_cannot_be_hidden_by_correct_image_and_price() -> None:
    expected = _example()
    actual = deepcopy(expected)
    actual["expected_name_bounds"] = _role(0.28, 0.04, 0.60, 0.10)

    result = compare_slot_reconstruction(expected, actual)

    assert result["roles"]["image"]["iou"] == pytest.approx(1.0)
    assert result["roles"]["priceblock"]["iou"] == pytest.approx(1.0)
    assert result["roles"]["unit"]["iou"] == pytest.approx(1.0)
    assert result["roles"]["name"]["iou"] < 1.0
    assert result["roles"]["name"]["center_distance"] > 0


def test_card_and_product_center_use_page_relative_geometry() -> None:
    expected = _example()
    actual = deepcopy(expected)
    actual["expected_card_bounds"]["relative_page_x"] += 0.05
    actual["expected_card_bounds"]["relative_page_y"] += 0.02

    result = compare_slot_reconstruction(expected, actual)

    assert result["card_bounds"]["x_error"] == pytest.approx(0.05)
    assert result["card_bounds"]["y_error"] == pytest.approx(0.02)
    assert result["product_center"]["dx"] == pytest.approx(0.05)
    assert result["product_center"]["dy"] == pytest.approx(0.02)
    assert result["product_center"]["distance"] > 0
