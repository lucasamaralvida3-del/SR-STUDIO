from __future__ import annotations

import pytest

from srstudio.graphics2.image_fill import (
    drawingml_fill_destination,
    has_drawingml_fill_rect,
    normalize_fill_rect,
)


def test_explicit_zero_fill_rect_is_still_a_drawingml_stretch_contract():
    assert has_drawingml_fill_rect({"l": 0, "t": 0, "r": 0, "b": 0})
    assert not has_drawingml_fill_rect({})
    assert not has_drawingml_fill_rect(None)


def test_quinta_file_negative_fill_rect_expands_blip_outside_shape():
    # Valor real observado nas páginas oficiais da Quinta Filé.
    destination = drawingml_fill_destination(
        100,
        80,
        {"l": -0.30959, "t": 0, "r": -0.30437, "b": 0},
    )

    assert destination.x == pytest.approx(-30.959)
    assert destination.y == pytest.approx(0)
    assert destination.width == pytest.approx(161.396)
    assert destination.height == pytest.approx(80)


def test_raw_ooxml_units_are_accepted_for_round_trip_compatibility():
    normalized = normalize_fill_rect({"l": -30959, "t": 0, "r": -30437, "b": -30482})

    assert normalized == pytest.approx(
        {"l": -0.30959, "t": 0.0, "r": -0.30437, "b": -0.30482}
    )


def test_positive_offsets_inset_the_fill_rectangle():
    destination = drawingml_fill_destination(
        200,
        100,
        {"l": 0.25, "t": 0.10, "r": 0.20, "b": 0.30},
    )

    assert (destination.x, destination.y) == pytest.approx((50, 10))
    assert (destination.width, destination.height) == pytest.approx((110, 60))


def test_preview_can_pre_mirror_fill_geometry_without_changing_final_size():
    normal = drawingml_fill_destination(
        200,
        100,
        {"l": -0.20, "t": -0.10, "r": -0.05, "b": -0.30},
    )
    mirrored = drawingml_fill_destination(
        200,
        100,
        {"l": -0.20, "t": -0.10, "r": -0.05, "b": -0.30},
        mirror_x=True,
        mirror_y=True,
    )

    assert mirrored.width == pytest.approx(normal.width)
    assert mirrored.height == pytest.approx(normal.height)
    assert mirrored.x == pytest.approx(200 - (normal.x + normal.width))
    assert mirrored.y == pytest.approx(100 - (normal.y + normal.height))


def test_degenerate_fill_rect_falls_back_to_shape_bounds_instead_of_hiding_image():
    destination = drawingml_fill_destination(
        300,
        200,
        {"l": 0.75, "t": 0.75, "r": 0.75, "b": 0.75},
    )

    assert (destination.x, destination.y, destination.width, destination.height) == pytest.approx(
        (0, 0, 300, 200)
    )
