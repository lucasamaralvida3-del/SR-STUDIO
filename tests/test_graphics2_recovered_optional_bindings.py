from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks
from srstudio.graphics2.semantic_recovery import recover_canva_semantic_cards


def _text(name: str, text: str, x: float, y: float, w: float, h: float, size: float = 24) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Arial", "font_size": size},
        metadata={"source": "pptx", "source_name": name},
    )


def _document(*, club_label: str = "CLUBE SR") -> tuple[GraphicsDocument, dict[str, GraphicsNode]]:
    document = GraphicsDocument(name="Recuperação clube e limite")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group Product 1",
        transform=Transform(x=100, y=90, width=500, height=470),
        metadata={
            "source": "pptx",
            "source_name": "Group Product 1",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    nodes = {
        "name": _text("Product Name", "ARROZ PATOSUL 5KG", 145, 110, 350, 55, 28),
        "image": GraphicsNode(
            kind=NodeKind.IMAGE,
            name="Picture 1",
            locked=True,
            transform=Transform(x=145, y=170, width=210, height=155),
            metadata={"source": "pptx", "source_name": "Picture 1"},
        ),
        "currency": _text("Currency", "R$", 330, 330, 45, 55, 24),
        "reais": _text("Whole", "25", 375, 305, 105, 105, 58),
        "cents": _text("Cents", ",77", 480, 315, 58, 48, 24),
        "unit": _text("Unit", "/UN", 480, 365, 55, 38, 20),
        "limit": _text("Limit", "LIMITE DE 4UN POR CPF", 145, 420, 220, 38, 16),
        "club_label": _text("Club Label", club_label, 370, 415, 145, 32, 16),
        "app_currency": _text("App Currency", "R$", 360, 460, 38, 42, 18),
        "app_reais": _text("App Whole", "22", 398, 445, 70, 72, 40),
        "app_cents": _text("App Cents", ",99", 468, 450, 48, 34, 18),
        "app_unit": _text("App Unit", "/UN", 468, 486, 48, 30, 15),
    }
    for node in nodes.values():
        page.add_node(node, parent_id=group.id)
    document.metadata["products"] = [
        {
            "id": "p1",
            "display_name": "AÇÚCAR DELTA 5KG",
            "price": "18,66",
            "unit": "UN",
            "limit": "6UN",
            "app_price": "16,49",
        }
    ]
    return document, nodes


def test_recovered_group_promotes_limit_and_secondary_price_only_with_local_club_signal():
    document, nodes = _document()
    semantic = build_semantic_blocks(document)
    assert semantic.recovered_product_cards == 1
    page = document.active_page
    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.metadata["semantic_recovered"] is True
    assert BindingRole.LIMIT.value not in slot.node_by_role
    assert not slot.metadata.get("extra_bindings")
    assert len((page.metadata["semantic_blocks"][slot.metadata["semantic_product_card_id"]]["metadata"]["price_blocks"])) == 2

    report = recover_canva_semantic_cards(document)

    assert report.warnings == []
    page = document.active_page
    slot = next(iter(page.slots.values()))
    assert slot.node_by_role[BindingRole.LIMIT.value] == nodes["limit"].id
    extras = slot.metadata["extra_bindings"]
    assert extras["app_price_currency"] == [nodes["app_currency"].id]
    assert extras["app_price_integer"] == [nodes["app_reais"].id]
    assert extras["app_price_cents"] == [nodes["app_cents"].id]
    assert extras["app_unit"] == [nodes["app_unit"].id]
    assert document.metadata["semantic_recovery_complete"]["recovered_limit_bindings"] == 1
    assert document.metadata["semantic_recovery_complete"]["recovered_app_price_bindings"] == 1

    price_ids = slot.metadata["semantic_price_block_ids"]
    assert len(price_ids) == 2
    app_blocks = [page.metadata["semantic_blocks"][block_id] for block_id in price_ids if page.metadata["semantic_blocks"][block_id]["metadata"].get("app_price")]
    assert len(app_blocks) == 1
    assert app_blocks[0]["slot_id"] == slot.id
    assert app_blocks[0]["metadata"]["recovered_app_price"] is True

    router = GraphicsCommandRouter(GraphicsSession(document))
    rebound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product_id": "p1"})
    assert rebound.ok and rebound.changed
    page = router.session.page
    assert page.node(nodes["limit"].id).text == "LIMITE DE 6UN POR CPF"
    assert page.node(nodes["app_currency"].id).text == "R$"
    assert page.node(nodes["app_reais"].id).text == "16"
    assert page.node(nodes["app_cents"].id).text == ",49"
    assert page.node(nodes["app_unit"].id).text == "/UN"
    assert page.node(nodes["reais"].id).text == "18"
    assert page.node(nodes["cents"].id).text == ",66"


def test_recovered_secondary_price_is_not_invented_without_explicit_club_or_app_label():
    document, nodes = _document(club_label="PREÇO ESPECIAL")
    build_semantic_blocks(document)
    recover_canva_semantic_cards(document)

    slot = next(iter(document.active_page.slots.values()))
    assert slot.node_by_role[BindingRole.LIMIT.value] == nodes["limit"].id
    extras = slot.metadata.get("extra_bindings") or {}
    assert not any(str(role).startswith("app_price_") or str(role) == "app_unit" for role in extras)
    assert document.metadata["semantic_recovery_complete"]["recovered_limit_bindings"] == 1
    assert document.metadata["semantic_recovery_complete"]["recovered_app_price_bindings"] == 0


def test_ambiguous_two_secondary_prices_near_same_club_label_are_rejected():
    document, nodes = _document()
    page = document.active_page
    group_id = page.node(nodes["name"].id).parent_id
    assert group_id
    # Um terceiro preço completo dividido e praticamente equidistante do rótulo
    # torna a intenção ambígua. A recuperação deve preservar o layout sem bind.
    third = {
        "currency": _text("Third Currency", "R$", 250, 460, 38, 42, 18),
        "reais": _text("Third Whole", "20", 288, 445, 70, 72, 40),
        "cents": _text("Third Cents", ",50", 358, 450, 48, 34, 18),
        "unit": _text("Third Unit", "/UN", 358, 486, 48, 30, 15),
    }
    for node in third.values():
        page.add_node(node, parent_id=group_id)

    build_semantic_blocks(document)
    recover_canva_semantic_cards(document)

    slot = next(iter(document.active_page.slots.values()))
    extras = slot.metadata.get("extra_bindings") or {}
    assert not any(str(role).startswith("app_price_") or str(role) == "app_unit" for role in extras)
