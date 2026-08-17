from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.professional_actions import G2ProfessionalActions


def test_professional_actions_facade_coordinates_safe_editor_services():
    document = GraphicsDocument(name="Encartes")
    page = document.active_page
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        text="OFERTA",
        transform=Transform(x=20, y=20, width=180, height=50),
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        transform=Transform(x=20, y=90, width=180, height=150),
        style={"fit": "cover", "zoom": 1.25},
    )
    page.add_node(text)
    page.add_node(image)
    document.add_page(GraphicsPage(name="Página 2"))
    document.active_page_id = page.id

    actions = G2ProfessionalActions(GraphicsSession(document))

    assert actions.edit_text_style(text.id, font_size=48, align="center")
    assert actions.session.page.node(text.id).style["font_size"] == 48
    assert actions.replace_image(image.id, "C:/produtos/acem.png")
    assert actions.session.page.node(image.id).style["zoom"] == 1.25

    copied_id = actions.duplicate_page(page.id, name="Página 1 cópia")
    assert copied_id
    assert actions.session.document.page(copied_id).name == "Página 1 cópia"
    assert actions.rename_page(copied_id, "Quinta Filé 2")
    assert actions.session.document.page(copied_id).name == "Quinta Filé 2"
    assert actions.reorder_page(copied_id, 0)
    assert actions.session.document.pages[0].id == copied_id

    report = actions.inspect_usability()
    assert report.blockers == 0

    assert actions.delete_page(copied_id)
    assert actions.session.document.page(copied_id) is None
