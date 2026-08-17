from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.professional_command_router import ProfessionalGraphicsCommandRouter


def _router():
    document = GraphicsDocument(name="Router profissional")
    page = document.active_page
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Título",
        text="OFERTA",
        transform=Transform(x=20, y=20, width=180, height=50),
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem",
        transform=Transform(x=30, y=100, width=160, height=140),
        style={"fit": "cover", "zoom": 1.3},
    )
    page.add_node(text)
    page.add_node(image)
    return ProfessionalGraphicsCommandRouter(GraphicsSession(document)), text.id, image.id


def test_professional_router_overrides_duplicate_page_with_fresh_ids():
    router, text_id, _ = _router()
    source = router.session.page
    source_nodes = set(source.nodes)

    result = router.dispatch({"name": "duplicate_page", "name_value": "Página 2"})

    assert result.ok and result.changed
    assert len(router.session.document.pages) == 2
    copied = router.session.document.page(result.payload["page_id"])
    assert copied is not None
    assert copied.name == "Página 2"
    assert set(copied.nodes).isdisjoint(source_nodes)
    assert text_id not in copied.nodes


def test_professional_router_keeps_legacy_commands_and_adds_professional_actions():
    router, text_id, image_id = _router()

    assert router.dispatch({"name": "select", "node_id": text_id}).ok
    moved = router.dispatch({"name": "move", "dx": 5, "dy": 7, "snap": False})
    assert moved.ok and moved.changed
    assert router.session.page.node(text_id).transform.x == 25
    assert router.session.page.node(text_id).transform.y == 27

    styled = router.dispatch({"name": "edit_text_style", "node_id": text_id, "font_size": 44, "color": "#123456"})
    assert styled.ok and styled.changed
    assert router.session.page.node(text_id).style["font_size"] == 44

    replaced = router.dispatch({"name": "replace_image", "node_id": image_id, "source": "C:/produtos/acem.png"})
    assert replaced.ok and replaced.changed
    image = router.session.page.node(image_id)
    assert image.style["zoom"] == 1.3
    assert image.metadata["bound_image_source"].endswith("acem.png")


def test_professional_router_exposes_context_and_usability_diagnostics():
    router, text_id, _ = _router()
    context = router.dispatch({"name": "inspect_properties", "selection": [text_id]})
    assert context.ok
    assert context.payload["target_type"] == "text"
    assert "font_family" in context.payload["properties"]

    report = router.dispatch({"name": "inspect_usability"})
    assert report.ok
    assert report.payload["blockers"] == 0


def test_professional_router_page_delete_never_removes_last_page():
    router, _, _ = _router()
    page_id = router.session.page.id
    result = router.dispatch({"name": "delete_page", "page_id": page_id})
    assert result.ok
    assert not result.changed
    assert len(router.session.document.pages) == 1
