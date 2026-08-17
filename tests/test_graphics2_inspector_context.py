from __future__ import annotations

from srstudio.graphics2.inspector_context import inspector_context
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind


def test_inspector_context_is_focused_by_node_type():
    document = GraphicsDocument(name="Inspector")
    page = document.active_page
    text = GraphicsNode(kind=NodeKind.TEXT, name="Título", text="OFERTA")
    image = GraphicsNode(kind=NodeKind.IMAGE, name="Produto")
    shape = GraphicsNode(kind=NodeKind.RECT, name="Faixa")
    page.add_node(text)
    page.add_node(image)
    page.add_node(shape)

    text_context = inspector_context(page, [text.id])
    assert text_context.target_type == "text"
    assert "font_family" in text_context.properties
    assert "replace_image" not in text_context.properties

    image_context = inspector_context(page, [image.id])
    assert image_context.target_type == "image"
    assert "replace_image" in image_context.properties
    assert "crop_left" in image_context.properties
    assert "font_family" not in image_context.properties

    shape_context = inspector_context(page, [shape.id])
    assert shape_context.target_type == "shape"
    assert "fill" in shape_context.properties
    assert "stroke" in shape_context.properties


def test_inspector_context_handles_page_and_multiselection_without_noise():
    document = GraphicsDocument(name="Inspector")
    page = document.active_page
    first = GraphicsNode(kind=NodeKind.TEXT, text="A")
    second = GraphicsNode(kind=NodeKind.IMAGE)
    page.add_node(first)
    page.add_node(second)

    page_context = inspector_context(page, [])
    assert page_context.target_type == "page"
    assert page_context.properties == ("name", "width", "height", "background", "guides")

    multi = inspector_context(page, [first.id, second.id])
    assert multi.multi_selection is True
    assert multi.target_type == "multi"
    assert "align_center" in multi.properties
    assert "font_size" not in multi.properties
    assert "crop_left" not in multi.properties


def test_inspector_context_prioritizes_semantic_product_card_and_price_block():
    document = GraphicsDocument(name="Semântica")
    page = document.active_page
    page.metadata["semantic_blocks"] = {
        "card-1": {
            "id": "card-1",
            "kind": "product_card",
            "name": "Produto destaque",
            "members": [],
        },
        "price-1": {
            "id": "price-1",
            "kind": "price_block",
            "name": "Preço principal",
            "members": [],
        },
    }

    card = inspector_context(page, ["card-1"])
    assert card.semantic is True
    assert card.target_type == "product_card"
    assert "replace_product" in card.properties
    assert "app_price" in card.properties

    price = inspector_context(page, ["price-1"])
    assert price.semantic is True
    assert price.target_type == "price_block"
    assert "price" in price.properties
    assert "currency" in price.properties
    assert "replace_image" not in price.properties
