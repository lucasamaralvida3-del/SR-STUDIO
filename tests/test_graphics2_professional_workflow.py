from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.semantic_blocks import build_semantic_blocks
from srstudio.graphics2.usability_gate import inspect_encarte_usability


def _build_product_slot(session: GraphicsSession):
    page = session.page
    roles = {}
    specs = [
        (BindingRole.IMAGE, NodeKind.IMAGE, "", 80, 250, 300, 260),
        (BindingRole.NAME, NodeKind.TEXT, "PRODUTO", 80, 520, 300, 60),
        (BindingRole.CURRENCY, NodeKind.TEXT, "R$", 80, 600, 50, 50),
        (BindingRole.PRICE_REAIS, NodeKind.TEXT, "0", 130, 580, 110, 80),
        (BindingRole.PRICE_CENTS, NodeKind.TEXT, ",00", 240, 585, 80, 45),
        (BindingRole.UNIT, NodeKind.TEXT, "/KG", 245, 630, 80, 35),
        (BindingRole.LIMIT, NodeKind.TEXT, "", 80, 680, 300, 30),
    ]
    for role, kind, text, x, y, width, height in specs:
        node = GraphicsNode(
            kind=kind,
            name=role.value,
            text=text,
            transform=Transform(x=x, y=y, width=width, height=height),
            binding_role=role,
        )
        page.add_node(node)
        roles[role] = node.id
    return session.create_slot("Produto destaque", roles)


def test_professional_encarte_edit_save_reopen_and_duplicate_page(tmp_path: Path):
    session = GraphicsSession(GraphicsDocument(name="Quinta Filé"))
    slot = _build_product_slot(session)

    session.bind_product(
        slot.id,
        {
            "id": "acem-kg",
            "display_name": "ACÉM BOVINO",
            "price": "33,64",
            "unit": "KG",
            "cpf_limit": "6KG",
        },
    )
    build_semantic_blocks(session.document)

    page = session.page
    name_id = slot.node_by_role[BindingRole.NAME.value]
    reais_id = slot.node_by_role[BindingRole.PRICE_REAIS.value]
    cents_id = slot.node_by_role[BindingRole.PRICE_CENTS.value]
    unit_id = slot.node_by_role[BindingRole.UNIT.value]

    assert page.nodes[name_id].text == "ACÉM BOVINO"
    assert page.nodes[reais_id].text == "33"
    assert page.nodes[cents_id].text == ",64"
    assert page.nodes[unit_id].text == "/KG"

    original_x = page.nodes[name_id].transform.x
    session.select(name_id)
    session.move_selected(20, 0)
    assert page.nodes[name_id].transform.x == original_x + 20
    assert session.undo() is True
    assert session.page.nodes[name_id].transform.x == original_x
    assert session.redo() is True
    assert session.page.nodes[name_id].transform.x == original_x + 20

    duplicated_page_id = session.add_page(duplicate_active=True)
    assert len(session.document.pages) == 2
    assert session.document.active_page_id == duplicated_page_id
    assert session.page.name.endswith("cópia")
    assert next(iter(session.page.slots.values())).page_id == duplicated_page_id

    build_semantic_blocks(session.document)
    gate_before_save = inspect_encarte_usability(session.document, require_bound_product=True)
    assert gate_before_save.ready is True

    target = save_package(session.document, tmp_path / "quinta-file.srscene", embed_local_assets=False)
    restored = load_package(target)
    gate_after_open = inspect_encarte_usability(restored, require_bound_product=True)

    assert len(restored.pages) == 2
    assert restored.active_page_id == duplicated_page_id
    assert gate_after_open.ready is True
    assert gate_after_open.metrics["product_cards"] >= 2
    assert gate_after_open.metrics["price_blocks"] >= 2
