from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.qt_host import prepare_qml_payload
import srstudio.graphics2.qt_host as qt_host


def _preview_node(document: GraphicsDocument, node: GraphicsNode) -> dict:
    document.active_page.add_node(node)
    payload = GraphicsCommandRouter(GraphicsSession(document)).payload()
    preview = prepare_qml_payload(payload)
    return preview["pages"][0]["nodes"][node.id]


def test_qml_preview_keeps_explicit_autofit_for_semantic_price_tokens():
    document = GraphicsDocument()
    price = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Reais",
        text="25",
        transform=Transform(width=100, height=80),
        style={"fit_inside_box": True, "nowrap": True, "font_size": 80},
        metadata={"semantic_price_block_id": "priceblock:test"},
    )

    preview_node = _preview_node(document, price)

    assert preview_node["style"]["fit_inside_box"] is True
    assert preview_node["style"]["nowrap"] is True
    assert preview_node["text"] == "25"
    assert document.active_page.node(price.id).style["fit_inside_box"] is True
    assert document.active_page.node(price.id).style["nowrap"] is True


def test_qml_preview_nowrap_without_autofit_preserves_original_scene_contract():
    document = GraphicsDocument()
    title = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Título",
        text="OFERTA SEMANAL",
        transform=Transform(width=200, height=50),
        style={"fit_inside_box": False, "nowrap": True, "font_size": 32},
    )

    preview_node = _preview_node(document, title)

    assert preview_node["style"]["fit_inside_box"] is False
    assert preview_node["style"]["nowrap"] is True
    assert preview_node["text"] == "OFERTA SEMANAL"
    assert "semantic_preview_fixed_size" not in preview_node["style"]
    assert "semantic_preview_nowrap" not in preview_node["style"]
    assert document.active_page.node(title.id).text == "OFERTA SEMANAL"
    assert document.active_page.node(title.id).style["nowrap"] is True


def test_qml_preview_preserves_priceblock_overflow_only_fit_policy():
    document = GraphicsDocument()
    cents = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Centavos",
        text=",98",
        transform=Transform(width=80, height=60),
        style={
            "fit_inside_box": False,
            "nowrap": True,
            "semantic_fit_policy": "overflow_only",
            "font_size": 48,
        },
        metadata={"semantic_price_block_id": "priceblock:test"},
    )

    preview_node = _preview_node(document, cents)

    assert preview_node["style"]["nowrap"] is True
    assert preview_node["style"]["semantic_fit_policy"] == "overflow_only"
    assert preview_node["text"] == ",98"


def test_graphics_editor_qml_separates_nowrap_from_autofit_policy():
    qml = (Path(qt_host.__file__).with_name("qml") / "GraphicsEditor.qml").read_text(encoding="utf-8")

    assert 'property bool fitTextInside: !!modelData.style.fit_inside_box || String(modelData.style.semantic_fit_policy || "").toLowerCase() === "overflow_only"' in qml
    assert "wrapMode: modelData.style.nowrap ? Text.NoWrap : Text.WordWrap" in qml
    assert "fontSizeMode: fitTextInside ? Text.Fit : Text.FixedSize" in qml
    assert "elide: fitTextInside ? Text.ElideNone : (modelData.style.nowrap ? Text.ElideNone : Text.ElideRight)" in qml
    assert "fontSizeMode: (modelData.style.fit_inside_box || modelData.style.nowrap) ? Text.Fit : Text.FixedSize" not in qml
