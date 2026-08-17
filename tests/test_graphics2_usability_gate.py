from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, SmartSlot, Transform
from srstudio.graphics2.page_clone import clone_page_with_fresh_ids
from srstudio.graphics2.usability_gate import inspect_g2_usability


def _product_nodes(page: GraphicsPage, *, offset: float = 0.0):
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        text="PRODUTO",
        transform=Transform(x=50 + offset, y=50, width=180, height=40),
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem",
        transform=Transform(x=50 + offset, y=100, width=160, height=120),
    )
    price = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Preço",
        text="9",
        transform=Transform(x=80 + offset, y=230, width=80, height=70),
    )
    for node in (name, image, price):
        page.add_node(node)
    slot = SmartSlot(
        page_id=page.id,
        node_by_role={
            BindingRole.NAME.value: name.id,
            BindingRole.IMAGE.value: image.id,
            BindingRole.PRICE_REAIS.value: price.id,
        },
        product_id=f"produto-{offset}",
    )
    page.slots[slot.id] = slot
    return slot


def test_usability_gate_accepts_multi_product_editable_flyer_scene():
    document = GraphicsDocument(name="Encartes")
    page = document.active_page
    _product_nodes(page, offset=0)
    _product_nodes(page, offset=300)

    report = inspect_g2_usability(document, require_multi_product_page=True)

    assert report.professional_usable
    assert report.blockers == 0
    assert report.page_count == 1
    assert report.populated_pages == 1
    assert report.smart_slots == 2
    assert report.bound_slots == 2
    assert report.editable_text_nodes >= 2
    assert report.image_nodes == 2


def test_usability_gate_rejects_dangling_slot_binding():
    document = GraphicsDocument(name="Binding inválido")
    page = document.active_page
    node = GraphicsNode(kind=NodeKind.TEXT, text="PRODUTO")
    page.add_node(node)
    slot = SmartSlot(
        page_id=page.id,
        node_by_role={BindingRole.NAME.value: "node_inexistente"},
    )
    page.slots[slot.id] = slot

    report = inspect_g2_usability(document)

    assert not report.professional_usable
    assert any(issue.code == "DANGLING_SLOT_BINDING" for issue in report.issues)


def test_usability_gate_detects_legacy_duplicate_page_identity():
    document = GraphicsDocument(name="Duplicação insegura")
    page = document.active_page
    _product_nodes(page)

    # Reproduz a estratégia histórica de deepcopy + troca somente do page.id.
    duplicate = deepcopy(page)
    duplicate.id = "page_copy"
    for slot in duplicate.slots.values():
        slot.page_id = duplicate.id
    document.pages.append(duplicate)

    report = inspect_g2_usability(document)

    assert not report.professional_usable
    assert any(issue.code == "DUPLICATE_NODE_ID_ACROSS_PAGES" for issue in report.issues)
    assert any(issue.code == "DUPLICATE_SLOT_ID_ACROSS_PAGES" for issue in report.issues)


def test_safe_clone_removes_cross_page_identity_collisions():
    document = GraphicsDocument(name="Duplicação segura")
    page = document.active_page
    _product_nodes(page)
    clone = clone_page_with_fresh_ids(page, rebuild_semantics=False)
    document.pages.append(clone)

    report = inspect_g2_usability(document)

    assert report.professional_usable
    assert not any(issue.code.startswith("DUPLICATE_") for issue in report.issues)
