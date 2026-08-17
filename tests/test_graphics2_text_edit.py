from __future__ import annotations

from copy import deepcopy

import pytest

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.text_edit import update_text_style


def _session():
    document = GraphicsDocument(name="Texto")
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        text="OFERTA",
        transform=Transform(x=20, y=30, width=300, height=80),
        style={
            "font_family": "Segoe UI",
            "font_size": 32,
            "font_size_unit": "pt",
            "font_weight": 700,
            "align": "center",
            "line_spacing_px": 40,
        },
    )
    document.active_page.add_node(node)
    return GraphicsSession(document), node.id


def test_update_text_style_preserves_geometry_and_is_undoable():
    session, node_id = _session()
    node = session.page.node(node_id)
    before_transform = deepcopy(node.transform)
    before_style = deepcopy(node.style)
    assert update_text_style(
        session,
        node_id,
        font_family="Anton",
        font_size=46,
        font_weight=800,
        italic=True,
        color="#0F5BD8",
        align="left",
        vertical_align="top",
        letter_spacing=1.5,
        line_spacing=1.1,
        opacity=0.9,
    )
    node = session.page.node(node_id)
    assert node.transform == before_transform
    assert node.style["font_family"] == "Anton"
    assert node.style["font_size"] == 46
    assert node.style["font_weight"] == 800
    assert node.style["italic"] is True
    assert node.style["color"] == "#0F5BD8"
    assert node.style["align"] == "left"
    assert node.style["vertical_align"] == "top"
    assert node.style["letter_spacing"] == 1.5
    assert node.style["line_spacing_percent"] == 1.1
    assert "line_spacing_px" not in node.style
    assert node.opacity == 0.9
    assert session.undo()
    restored = session.page.node(node_id)
    assert restored.style == before_style
    assert restored.transform == before_transform


def test_update_text_style_validates_alignment_and_locked_nodes():
    session, node_id = _session()
    with pytest.raises(ValueError):
        update_text_style(session, node_id, align="diagonal")
    session.page.node(node_id).locked = True
    assert not update_text_style(session, node_id, font_size=52)
