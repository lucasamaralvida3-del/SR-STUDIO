from __future__ import annotations

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.import_bridge import CanvaBindingService, _style_from_element, from_imported_project
from srstudio.graphics2.model import NodeKind
from srstudio.graphics2.operations import GraphicsSession


def _session_with_unit(template: str) -> tuple[GraphicsSession, str]:
    product = Product(display_name="ACÉM", price="25,77", unit="KG")
    card = ProductCard(id="slot-unit", product_id=product.id)
    page = Page(
        cards=[card],
        elements=[
            {
                "type": "text",
                "x": 10,
                "y": 10,
                "width": 60,
                "height": 30,
                "text": template,
                "template_text": template,
                "slot_id": card.id,
                "slot_role": "unit",
            }
        ],
    )
    document = from_imported_project(StudioProject(products=[product], pages=[page]))
    return GraphicsSession(document), card.id


def test_pptx_alignment_tokens_are_canonical_for_qml_and_qpainter():
    style = _style_from_element(
        {
            "font_name": "Anton",
            "font_size": 32,
            "align": "l",
            "vertical_anchor": "t",
            "canva_single_line": True,
        },
        NodeKind.TEXT,
    )

    assert style["align"] == "left"
    assert style["v_align"] == "top"

    centered = _style_from_element({"align": "ctr", "vertical_anchor": "ctr"}, NodeKind.TEXT)
    assert centered["align"] == "center"
    assert centered["v_align"] == "center"


def test_binding_preserves_unit_without_slash_when_canva_template_uses_plain_kg():
    session, slot_id = _session_with_unit("KG")
    node = session.page.node(session.page.slots[slot_id].node_by_role["unit"])
    before = (node.transform.x, node.transform.y, node.transform.width, node.transform.height)

    assert CanvaBindingService.bind(session, slot_id, {"id": "new", "price": "10,99", "unit": "UN"})

    assert node.text == "UN"
    assert (node.transform.x, node.transform.y, node.transform.width, node.transform.height) == before


def test_binding_preserves_slash_when_template_explicitly_uses_it():
    session, slot_id = _session_with_unit("/KG")
    node = session.page.node(session.page.slots[slot_id].node_by_role["unit"])

    assert CanvaBindingService.bind(session, slot_id, {"id": "new", "price": "10,99", "unit": "UN"})

    assert node.text == "/UN"
