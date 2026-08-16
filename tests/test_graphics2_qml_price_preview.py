from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.qt_host import prepare_qml_payload


def test_qml_preview_disables_independent_text_fit_only_in_semantic_price_tokens():
    document = GraphicsDocument()
    page = document.active_page
    price = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Reais",
        text="25",
        transform=Transform(width=100, height=80),
        style={"fit_inside_box": True, "nowrap": True, "font_size": 80},
        metadata={"semantic_price_block_id": "priceblock:test"},
    )
    title = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Título",
        text="LINGUIÇA MISTA",
        transform=Transform(width=200, height=50),
        style={"fit_inside_box": True, "nowrap": True, "font_size": 32},
    )
    page.add_node(price)
    page.add_node(title)
    payload = GraphicsCommandRouter(GraphicsSession(document)).payload()

    preview = prepare_qml_payload(payload)
    preview_nodes = preview["pages"][0]["nodes"]

    assert preview_nodes[price.id]["style"]["fit_inside_box"] is False
    assert preview_nodes[price.id]["style"]["nowrap"] is False
    assert preview_nodes[price.id]["style"]["semantic_preview_fixed_size"] is True
    assert preview_nodes[title.id]["style"]["fit_inside_box"] is True
    assert preview_nodes[title.id]["style"]["nowrap"] is True
    # O contrato persistido não é alterado: a normalização existe só no JSON do preview.
    assert page.node(price.id).style["fit_inside_box"] is True
    assert page.node(price.id).style["nowrap"] is True
