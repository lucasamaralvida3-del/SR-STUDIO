from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2.asset_edit import replace_image
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def _session():
    document = GraphicsDocument(name="Imagem editável")
    node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=100, y=120, width=260, height=220),
        style={
            "fit": "cover",
            "zoom": 1.4,
            "focus_x": 0.2,
            "focus_y": 0.7,
            "flip_x": True,
            "crop": {"l": 0.1, "t": 0.0, "r": 0.05, "b": 0.0},
        },
    )
    document.active_page.add_node(node)
    return GraphicsSession(document), node.id


def test_replace_image_preserves_template_geometry_and_framing_by_default():
    session, node_id = _session()
    node = session.page.node(node_id)
    before_transform = deepcopy(node.transform)
    before_style = deepcopy(node.style)
    assert replace_image(session, node_id, "C:/produtos/acem.png")
    node = session.page.node(node_id)
    assert node.transform == before_transform
    assert node.style == before_style
    assert node.asset_id in session.document.assets
    assert node.metadata["bound_image_source"].endswith("acem.png")
    assert node.metadata["manual_image_replacement"] is True


def test_replace_image_can_reset_framing_explicitly_and_undo():
    session, node_id = _session()
    before = deepcopy(session.page.node(node_id).style)
    assert replace_image(session, node_id, "C:/produtos/linguica.png", reset_framing=True)
    node = session.page.node(node_id)
    assert node.style["fit"] == "contain"
    assert node.style["zoom"] == 1.0
    assert node.style["focus_x"] == 0.5
    assert node.style["focus_y"] == 0.5
    assert node.style["flip_x"] is False
    assert node.style["flip_y"] is False
    assert "crop" not in node.style
    assert session.undo()
    assert session.page.node(node_id).style == before


def test_replace_image_refuses_locked_or_non_image_nodes():
    session, node_id = _session()
    session.page.node(node_id).locked = True
    assert not replace_image(session, node_id, "C:/produto.png")
    text = GraphicsNode(kind=NodeKind.TEXT, text="não imagem")
    session.page.add_node(text)
    assert not replace_image(session, text.id, "C:/produto.png")
