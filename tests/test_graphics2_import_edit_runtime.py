from __future__ import annotations

from srstudio.graphics2 import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.import_edit_runtime import apply_import_editability


def _node(kind: NodeKind, *, locked: bool = True, visible: bool = True, template_hidden: bool = False) -> GraphicsNode:
    return GraphicsNode(
        kind=kind,
        locked=locked,
        visible=visible,
        transform=Transform(x=10, y=10, width=120, height=60),
        metadata={"source": "pptx", "template_hidden": template_hidden},
    )


def test_import_editability_unlocks_visible_content_but_keeps_template_structure_protected():
    document = GraphicsDocument(name="PPTX real")
    page = document.active_page
    text = _node(NodeKind.TEXT)
    image = _node(NodeKind.IMAGE)
    rect = _node(NodeKind.RECT)
    hidden_text = _node(NodeKind.TEXT, visible=False)
    template_hidden = _node(NodeKind.TEXT, template_hidden=True)
    already_editable = _node(NodeKind.TEXT, locked=False)

    for node in (text, image, rect, hidden_text, template_hidden, already_editable):
        page.add_node(node)

    report = apply_import_editability(document)

    assert text.locked is False
    assert image.locked is False
    assert already_editable.locked is False
    assert text.metadata["import_editable"] is True
    assert image.metadata["import_editable"] is True
    assert rect.locked is True
    assert hidden_text.locked is True
    assert template_hidden.locked is True
    assert report["unlocked_text"] == 1
    assert report["unlocked_images"] == 1
    assert report["protected_structural"] == 1
    assert report["already_editable"] == 1
    assert document.metadata["import_editability"]["policy"] == "content-v1"


def test_import_editability_is_idempotent():
    document = GraphicsDocument()
    text = _node(NodeKind.TEXT)
    document.active_page.add_node(text)

    first = apply_import_editability(document)
    second = apply_import_editability(document)

    assert first["unlocked_text"] == 1
    assert second["unlocked_text"] == 0
    assert second["already_editable"] == 1
    assert text.locked is False
