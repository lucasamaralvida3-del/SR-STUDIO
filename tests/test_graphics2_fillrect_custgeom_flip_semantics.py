from __future__ import annotations

from dataclasses import dataclass
import math

import pytest

from srstudio.graphics2.image_fill import drawingml_fill_destination


@dataclass(frozen=True)
class _Rect:
    x: float
    y: float
    width: float
    height: float


def _map(points, target: _Rect, *, source_width: float = 100.0, source_height: float = 100.0):
    return [
        (
            target.x + x * target.width / source_width,
            target.y + y * target.height / source_height,
        )
        for x, y in points
    ]


def _mirror(points, target: _Rect, *, horizontal: bool = False, vertical: bool = False):
    cx = target.x + target.width / 2.0
    cy = target.y + target.height / 2.0
    result = []
    for x, y in points:
        if horizontal:
            x = 2.0 * cx - x
        if vertical:
            y = 2.0 * cy - y
        result.append((x, y))
    return result


def _rotate(points, target: _Rect, degrees: float):
    angle = math.radians(degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    cx = target.x + target.width / 2.0
    cy = target.y + target.height / 2.0
    result = []
    for x, y in points:
        dx = x - cx
        dy = y - cy
        result.append((cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a))
    return result


def _absolute_destination(target: _Rect, fill_rect: dict[str, float]) -> _Rect:
    local = drawingml_fill_destination(target.width, target.height, fill_rect)
    return _Rect(target.x + local.x, target.y + local.y, local.width, local.height)


def test_fixture_a_triangular_custgeom_negative_fillrect_control() -> None:
    destination = drawingml_fill_destination(
        200.0,
        100.0,
        {"l": -0.25, "t": -0.10, "r": -0.30, "b": -0.05},
    )
    assert destination.x == pytest.approx(-50.0)
    assert destination.y == pytest.approx(-10.0)
    assert destination.width == pytest.approx(310.0)
    assert destination.height == pytest.approx(115.0)


def test_fixture_b_curved_nonrect_positive_fillrect() -> None:
    target = _Rect(10.0, 20.0, 200.0, 100.0)
    curved = [(0.0, 50.0), (25.0, 0.0), (75.0, 0.0), (100.0, 50.0), (75.0, 100.0), (25.0, 100.0)]
    mapped = _map(curved, target)
    destination = drawingml_fill_destination(
        target.width,
        target.height,
        {"l": 0.10, "t": 0.20, "r": 0.15, "b": 0.05},
    )
    assert mapped[0] == pytest.approx((10.0, 70.0))
    assert (destination.x, destination.y, destination.width, destination.height) == pytest.approx((20.0, 20.0, 150.0, 75.0))


def test_fixture_c_negative_fillrect_only_horizontal_axis() -> None:
    destination = drawingml_fill_destination(
        200.0,
        100.0,
        {"l": -0.20, "t": 0.0, "r": -0.10, "b": 0.0},
    )
    assert (destination.x, destination.y, destination.width, destination.height) == pytest.approx((-40.0, 0.0, 260.0, 100.0))


def test_fixture_d_asymmetric_custgeom_flip_h_documents_current_g2_divergence() -> None:
    target = _Rect(10.0, 20.0, 200.0, 100.0)
    asymmetric = [(0.0, 0.0), (100.0, 20.0), (65.0, 100.0), (10.0, 70.0)]
    current_export_clip = _map(asymmetric, target)
    expected_drawingml_shape = _mirror(current_export_clip, target, horizontal=True)

    # Current production convention: IMAGE pixels are mirrored while custGeom
    # remains mapped to the unflipped target. DrawingML xfrm semantics require
    # the asymmetric geometry and picture fill to transform together.
    assert expected_drawingml_shape != current_export_clip

    # The Qt Quick provider pre-mirrors its local mask because QML mirrors the
    # composed Image afterwards. Net preview mask therefore returns to the same
    # unflipped geometry used by QPainter export.
    provider_pre_mirror = _mirror(current_export_clip, target, horizontal=True)
    provider_net_clip = _mirror(provider_pre_mirror, target, horizontal=True)
    assert provider_net_clip == pytest.approx(current_export_clip)


def test_fixture_e_asymmetric_custgeom_flip_v_documents_current_g2_divergence() -> None:
    target = _Rect(10.0, 20.0, 200.0, 100.0)
    asymmetric = [(0.0, 0.0), (100.0, 20.0), (65.0, 100.0), (10.0, 70.0)]
    current_export_clip = _map(asymmetric, target)
    expected_drawingml_shape = _mirror(current_export_clip, target, vertical=True)
    assert expected_drawingml_shape != current_export_clip

    provider_pre_mirror = _mirror(current_export_clip, target, vertical=True)
    provider_net_clip = _mirror(provider_pre_mirror, target, vertical=True)
    assert provider_net_clip == pytest.approx(current_export_clip)


def test_fixture_f_rotation_keeps_path_and_picture_fill_in_same_painter_reference() -> None:
    target = _Rect(10.0, 20.0, 200.0, 100.0)
    asymmetric = _map([(0.0, 0.0), (100.0, 20.0), (65.0, 100.0), (10.0, 70.0)], target)
    destination = _absolute_destination(target, {"l": -0.10, "t": 0.05, "r": 0.10, "b": -0.05})
    destination_corners = [(destination.x, destination.y), (destination.x + destination.width, destination.y + destination.height)]

    assert _rotate(asymmetric, target, 30.0) != asymmetric
    assert _rotate(destination_corners, target, 30.0) != destination_corners


def test_fixture_g_partially_outside_canvas_preserves_local_mapping() -> None:
    target = _Rect(-40.0, 30.0, 200.0, 100.0)
    asymmetric = _map([(0.0, 0.0), (100.0, 20.0), (65.0, 100.0), (10.0, 70.0)], target)
    destination = _absolute_destination(target, {"l": -0.10, "t": 0.0, "r": 0.0, "b": 0.0})

    assert asymmetric[0] == pytest.approx((-40.0, 30.0))
    assert (destination.x, destination.y, destination.width, destination.height) == pytest.approx((-60.0, 30.0, 220.0, 100.0))
