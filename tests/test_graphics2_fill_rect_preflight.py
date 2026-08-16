from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.preflight import run_preflight


def _document(fill_rect) -> GraphicsDocument:
    document = GraphicsDocument(name="fillRect preflight")
    document.active_page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            transform=Transform(x=10, y=10, width=300, height=200),
            style={
                "fit": "cover",
                "focus_x": 0.5,
                "focus_y": 0.5,
                "zoom": 1.0,
                "crop": {},
                "fill_rect": fill_rect,
            },
        )
    )
    return document


def _codes(document: GraphicsDocument) -> list[str]:
    return [issue.code for issue in run_preflight(document)]


def test_negative_drawingml_outsets_are_valid():
    assert "INVALID_IMAGE_FILL_RECT" not in _codes(
        _document({"l": -0.30959, "t": 0, "r": -0.30437, "b": -0.30482})
    )


def test_raw_ooxml_percentage_units_are_valid():
    assert "INVALID_IMAGE_FILL_RECT" not in _codes(
        _document({"l": -30959, "t": 0, "r": -30437, "b": -30482})
    )


def test_non_numeric_fill_rect_is_blocked():
    assert "INVALID_IMAGE_FILL_RECT" in _codes(
        _document({"l": "abc", "t": 0, "r": 0, "b": 0})
    )


def test_non_finite_fill_rect_is_blocked():
    assert "INVALID_IMAGE_FILL_RECT" in _codes(
        _document({"l": float("inf"), "t": 0, "r": 0, "b": 0})
    )


def test_fill_rect_that_collapses_shape_is_blocked():
    assert "INVALID_IMAGE_FILL_RECT" in _codes(
        _document({"l": 0.6, "t": 0, "r": 0.4, "b": 0})
    )
