from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from srstudio.graphics2.pptx_fidelity import A_NS, PptxFidelityReport, _path_commands


def _path(body: str) -> ET.Element:
    return ET.fromstring(f'<a:path xmlns:a="{A_NS}" w="200" h="200">{body}</a:path>')


def _endpoint(command: dict) -> tuple[float, float]:
    point = command["points"][-1]
    return float(point[0]), float(point[1])


def test_arc_to_is_normalized_to_cubic_bezier_for_qml_and_qpainter_parity():
    path = _path(
        "<a:moveTo><a:pt x=\"100\" y=\"50\"/></a:moveTo>"
        "<a:arcTo wR=\"50\" hR=\"50\" stAng=\"0\" swAng=\"5400000\"/>"
    )
    report = PptxFidelityReport()

    commands = _path_commands(path, report=report)

    assert [command["op"] for command in commands] == ["M", "C"]
    assert _endpoint(commands[-1]) == pytest.approx((50.0, 100.0), abs=1e-6)
    assert commands[-1]["source_op"] == "A"
    assert commands[-1]["source_arc"]["segments"] == 1
    assert report.drawingml_arcs_seen == 1
    assert report.drawingml_arcs_converted == 1
    assert report.drawingml_arcs_deferred == 0


def test_large_arc_is_split_into_at_most_quarter_turn_segments():
    path = _path(
        "<a:moveTo><a:pt x=\"100\" y=\"50\"/></a:moveTo>"
        "<a:arcTo wR=\"50\" hR=\"50\" stAng=\"0\" swAng=\"16200000\"/>"
    )

    commands = _path_commands(path)
    curves = [command for command in commands if command["op"] == "C"]

    assert len(curves) == 3
    assert [curve["source_arc"]["segment"] for curve in curves] == [1, 2, 3]
    assert _endpoint(curves[-1]) == pytest.approx((50.0, 0.0), abs=1e-6)


def test_negative_sweep_keeps_drawingml_clockwise_coordinate_contract():
    path = _path(
        "<a:moveTo><a:pt x=\"100\" y=\"50\"/></a:moveTo>"
        "<a:arcTo wR=\"50\" hR=\"50\" stAng=\"0\" swAng=\"-5400000\"/>"
    )

    commands = _path_commands(path)

    assert [command["op"] for command in commands] == ["M", "C"]
    assert _endpoint(commands[-1]) == pytest.approx((50.0, 0.0), abs=1e-6)


def test_unresolvable_arc_is_preserved_instead_of_silently_disappearing():
    path = _path('<a:arcTo wR="50" hR="50" stAng="0" swAng="5400000"/>')
    report = PptxFidelityReport()

    commands = _path_commands(path, report=report)

    assert commands == [{"op": "A", "wR": 50.0, "hR": 50.0, "stAng": 0.0, "swAng": 5400000.0}]
    assert report.drawingml_arcs_seen == 1
    assert report.drawingml_arcs_converted == 0
    assert report.drawingml_arcs_deferred == 1


def test_close_restores_subpath_start_for_following_arc():
    path = _path(
        "<a:moveTo><a:pt x=\"100\" y=\"50\"/></a:moveTo>"
        "<a:lnTo><a:pt x=\"120\" y=\"50\"/></a:lnTo>"
        "<a:close/>"
        "<a:arcTo wR=\"50\" hR=\"50\" stAng=\"0\" swAng=\"5400000\"/>"
    )

    commands = _path_commands(path)

    assert [command["op"] for command in commands] == ["M", "L", "Z", "C"]
    assert _endpoint(commands[-1]) == pytest.approx((50.0, 100.0), abs=1e-6)
