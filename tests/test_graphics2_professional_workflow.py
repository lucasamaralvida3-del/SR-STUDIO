from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.page_clone import duplicate_active_page
from srstudio.graphics2.semantic_blocks import build_semantic_blocks
from srstudio.graphics2.usability_gate import inspect_g2_usability


def _workflow_document() -> GraphicsDocument:
    document = GraphicsDocument(name="Fluxo profissional de encarte")
    page = document.active_page
    document.metadata["products"] = [
        {
            "id": "produto-1",
            "display_name": "ACÉM BOVINO",
            "price": "33,64",
            "unit": "KG",
            "image_path": "acém.png",
        },
        {
            "id": "produto-2",
            "display_name": "LINGUIÇA MISTA CASEIRA SR",
            "price": "25,77",
            "unit": "KG",
            "image_path": "linguiça.png",
        },
    ]

    for index in range(2):
        x = 60 + index * 420
        name = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"Nome {index + 1}",
            transform=Transform(x=x, y=80, width=300, height=50),
        )
        image = GraphicsNode(
            kind=NodeKind.IMAGE,
            name=f"Imagem {index + 1}",
            transform=Transform(x=x, y=145, width=250, height=190),
        )
        currency = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"R$ {index + 1}",
            transform=Transform(x=x, y=355, width=45, height=50),
        )
        reais = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"Reais {index + 1}",
            transform=Transform(x=x + 50, y=335, width=115, height=90),
        )
        cents = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"Centavos {index + 1}",
            transform=Transform(x=x + 170, y=345, width=65, height=45),
        )
        unit = GraphicsNode(
            kind=NodeKind.TEXT,
            name=f"Unidade {index + 1}",
            transform=Transform(x=x + 170, y=390, width=65, height=35),
        )
        for node in (name, image, currency, reais, cents, unit):
            page.add_node(node)

        slot = SmartSlot(
            name=f"Produto {index + 1}",
            page_id=page.id,
            node_by_role={
                BindingRole.NAME.value: name.id,
                BindingRole.IMAGE.value: image.id,
                BindingRole.CURRENCY.value: currency.id,
                BindingRole.PRICE_REAIS.value: reais.id,
                BindingRole.PRICE_CENTS.value: cents.id,
                BindingRole.UNIT.value: unit.id,
            },
        )
        page.slots[slot.id] = slot

    build_semantic_blocks(document)
    return document


def test_professional_flyer_core_workflow_roundtrips_without_identity_collisions(tmp_path: Path):
    document = _workflow_document()
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    slots = list(session.page.slots)

    first = router.dispatch({"name": "bind_product", "slot_id": slots[0], "product_id": "produto-1"})
    second = router.dispatch({"name": "bind_product", "slot_id": slots[1], "product_id": "produto-2"})
    assert first.ok and first.changed
    assert second.ok and second.changed

    first_slot = session.page.slots[slots[0]]
    first_name = session.page.node(first_slot.node_by_role[BindingRole.NAME.value])
    first_reais = session.page.node(first_slot.node_by_role[BindingRole.PRICE_REAIS.value])
    first_cents = session.page.node(first_slot.node_by_role[BindingRole.PRICE_CENTS.value])
    assert first_name is not None and first_name.text == "ACÉM BOVINO"
    assert first_reais is not None and first_reais.text == "33"
    assert first_cents is not None and first_cents.text == ",64"

    router.dispatch({"name": "select", "node_id": first_name.id})
    before_x = first_name.transform.x
    moved = router.dispatch({"name": "move", "dx": 18, "dy": 0, "snap": False})
    assert moved.ok and moved.changed
    assert session.page.node(first_name.id).transform.x == before_x + 18
    assert session.undo()
    assert session.page.node(first_name.id).transform.x == before_x
    assert session.redo()
    assert session.page.node(first_name.id).transform.x == before_x + 18

    source_page_id = session.page.id
    duplicate_id = duplicate_active_page(session, name="Página 2")
    assert duplicate_id != source_page_id
    assert len(session.document.pages) == 2

    report = inspect_g2_usability(session.document, require_multi_product_page=True)
    assert report.professional_usable
    assert report.blockers == 0

    target = tmp_path / "encarte.srscene"
    save_package(session.document, target, embed_local_assets=False)
    loaded = load_package(target)

    assert len(loaded.pages) == 2
    assert loaded.active_page_id == duplicate_id
    after = inspect_g2_usability(loaded, require_multi_product_page=True)
    assert after.professional_usable
    assert after.blockers == 0
