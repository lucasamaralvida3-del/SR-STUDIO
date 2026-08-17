from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_recovery import recover_canva_semantic_cards


def _text(name: str, text: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        metadata={"source": "pptx", "source_name": name},
    )


def test_recovered_spatial_optional_bindings_join_atomic_selection_and_copy_paste():
    document = GraphicsDocument(name="Spatial recovered card")
    page = document.active_page
    nodes = {
        "name": _text("Name", "CAFÉ CAJUBÁ 500G", 100, 90, 300, 45),
        "image": GraphicsNode(kind=NodeKind.IMAGE, name="Image", transform=Transform(x=120, y=150, width=170, height=140)),
        "currency": _text("Currency", "R$", 300, 300, 40, 45),
        "reais": _text("Whole", "18", 340, 280, 90, 90),
        "cents": _text("Cents", ",99", 430, 290, 50, 40),
        "unit": _text("Unit", "/UN", 430, 335, 50, 30),
        "limit": _text("Limit", "LIMITE DE 3UN POR CPF", 100, 390, 230, 35),
        "club": _text("Club", "CLUBE SR", 345, 390, 120, 30),
        "app_currency": _text("App Currency", "R$", 330, 430, 35, 38),
        "app_reais": _text("App Whole", "16", 365, 415, 70, 70),
        "app_cents": _text("App Cents", ",49", 435, 420, 45, 30),
        "app_unit": _text("App Unit", "/UN", 435, 452, 45, 28),
    }
    for node in nodes.values():
        page.add_node(node)

    slot = SmartSlot(
        id="slot_spatial",
        name="CAFÉ CAJUBÁ 500G",
        page_id=page.id,
        node_by_role={
            BindingRole.NAME.value: nodes["name"].id,
            BindingRole.IMAGE.value: nodes["image"].id,
            BindingRole.CURRENCY.value: nodes["currency"].id,
            BindingRole.PRICE_REAIS.value: nodes["reais"].id,
            BindingRole.PRICE_CENTS.value: nodes["cents"].id,
            BindingRole.UNIT.value: nodes["unit"].id,
        },
        confidence=0.9,
        metadata={
            "source": "canva-smart-slot",
            "semantic_recovered": True,
            "recovered_spatial": True,
            "semantic_product_card_id": "productcard:spatial",
            "semantic_price_block_ids": ["priceblock:primary"],
        },
    )
    page.slots[slot.id] = slot

    primary_members = [nodes[key].id for key in ("currency", "reais", "cents", "unit")]
    app_members = [nodes[key].id for key in ("app_currency", "app_reais", "app_cents", "app_unit")]
    initial_card_members = [nodes["name"].id, nodes["image"].id, *primary_members]
    for node_id in initial_card_members:
        page.nodes[node_id].metadata["semantic_product_card_id"] = "productcard:spatial"

    page.metadata["semantic_blocks"] = {
        "priceblock:primary": {
            "id": "priceblock:primary",
            "kind": "price_block",
            "slot_id": slot.id,
            "members": primary_members,
            "roles": {
                "currency": [nodes["currency"].id],
                "reais": [nodes["reais"].id],
                "cents": [nodes["cents"].id],
                "unit": [nodes["unit"].id],
            },
            "bounds": {"x": 300, "y": 280, "width": 180, "height": 85},
            "metadata": {"smart_slot_id": slot.id},
        },
        "priceblock:secondary": {
            "id": "priceblock:secondary",
            "kind": "price_block",
            "slot_id": "",
            "members": app_members,
            "roles": {
                "currency": [nodes["app_currency"].id],
                "reais": [nodes["app_reais"].id],
                "cents": [nodes["app_cents"].id],
                "unit": [nodes["app_unit"].id],
            },
            "bounds": {"x": 330, "y": 415, "width": 150, "height": 65},
            "metadata": {"recovered": True},
        },
        "productcard:spatial": {
            "id": "productcard:spatial",
            "kind": "product_card",
            "slot_id": slot.id,
            "members": list(initial_card_members),
            "roles": {
                BindingRole.NAME.value: [nodes["name"].id],
                BindingRole.IMAGE.value: [nodes["image"].id],
            },
            "bounds": {"x": 90, "y": 80, "width": 410, "height": 410},
            "metadata": {
                "source_group_id": "",
                "region": {"x": 80, "y": 70, "width": 440, "height": 440},
                "content_members": list(initial_card_members),
                "price_blocks": ["priceblock:primary", "priceblock:secondary"],
                "recovered": True,
                "atomic": True,
            },
        },
    }

    recover_canva_semantic_cards(document)

    card = page.metadata["semantic_blocks"]["productcard:spatial"]
    expected_optional = {nodes["limit"].id, *app_members}
    assert expected_optional.issubset(set(card["members"]))
    assert slot.node_by_role[BindingRole.LIMIT.value] == nodes["limit"].id
    assert slot.metadata["extra_bindings"]["app_price_integer"] == [nodes["app_reais"].id]

    router = GraphicsCommandRouter(GraphicsSession(document))
    selected = router.dispatch({"name": "select", "node_id": nodes["name"].id, "semantic": True, "semantic_scope": "card"})
    assert selected.ok
    assert expected_optional.issubset(router.session.selection)

    copied = router.dispatch({"name": "copy"})
    assert copied.ok and copied.payload["count"] == len(card["members"])
    pasted = router.dispatch({"name": "paste", "dx": 500, "dy": 0})
    assert pasted.ok and pasted.changed
    assert len(pasted.payload["slot_ids"]) == 1
    clone_slot = router.session.page.slots[pasted.payload["slot_ids"][0]]
    assert BindingRole.LIMIT.value in clone_slot.node_by_role
    assert clone_slot.metadata["extra_bindings"]["app_price_integer"]
