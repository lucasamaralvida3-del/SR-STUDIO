from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.semantic_blocks import build_semantic_blocks
from srstudio.graphics2.semantic_placeholders import recover_canva_image_placeholders


def _text(name: str, text: str, x: float, y: float, w: float, h: float, size: float = 30) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": size},
        metadata={"source_name": name},
    )


def _price(page, prefix: str, x: float, y: float, whole_text: str, cents_text: str):
    currency = _text(prefix + " R$", "R$", x, y + 30, 38, 48, 26)
    whole = _text(prefix + " whole", whole_text, x + 45, y, 100, 105, 76)
    cents = _text(prefix + " cents", cents_text, x + 145, y + 8, 45, 38, 28)
    unit = _text(prefix + " unit", "KG", x + 145, y + 55, 45, 35, 24)
    for node in (currency, whole, cents, unit):
        page.add_node(node)
    return currency, whole, cents, unit


def test_white_canva_backplate_creates_hidden_synthetic_image_slot():
    document = GraphicsDocument(name="Quinta Filé placeholder")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    name = _text("TextBox 125", "ACÉM BOVINO", 18, 458, 348, 44, 36)
    placeholder = GraphicsNode(
        kind=NodeKind.RECT,
        name="Freeform 13",
        locked=True,
        transform=Transform(x=40.6, y=502.6, width=288.5, height=243.9),
        z_index=20,
        style={"fill": "#FFFFFF", "stroke": "transparent"},
        metadata={"source_name": "Freeform 13", "grouped": True},
    )
    price = _price(page, "Acem", 233.3, 645.6, "33", ",64")
    page.add_node(name)
    page.add_node(placeholder)
    before_placeholder = deepcopy(placeholder.transform)

    semantic = build_semantic_blocks(document)
    assert semantic.recovered_smart_slots == 1
    slot = next(iter(page.slots.values()))
    assert "image" not in slot.node_by_role

    recovered = recover_canva_image_placeholders(document)

    assert recovered.placeholders_matched == 1
    assert recovered.synthetic_image_slots == 1
    assert slot.metadata["recovered_image_placeholder_id"] == placeholder.id
    image_id = slot.node_by_role["image"]
    image = page.node(image_id)
    assert image is not None
    assert image.kind is NodeKind.IMAGE
    assert image.visible is False
    assert image.metadata["semantic_synthetic_image_slot"] is True
    assert placeholder.transform == before_placeholder
    assert placeholder.transform.x < image.transform.x < placeholder.transform.x + placeholder.transform.width
    assert placeholder.transform.y < image.transform.y < placeholder.transform.y + placeholder.transform.height
    assert image.transform.y + image.transform.height <= price[1].transform.y


def test_binding_product_reveals_synthetic_image_without_moving_canva_artwork():
    document = GraphicsDocument(name="Quinta Filé bind placeholder")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    name = _text("Name", "CARNE DE SERENO", 468, 557, 200, 50, 32)
    placeholder = GraphicsNode(
        kind=NodeKind.RECT,
        name="Freeform 22",
        locked=True,
        transform=Transform(x=468.9, y=583.5, width=198.9, height=168.1),
        z_index=40,
        style={"fill": "#FFFFFF"},
        metadata={"source_name": "Freeform 22"},
    )
    currency, whole, cents, unit = _price(page, "Sereno", 601.8, 682.2, "42", ",66")
    page.add_node(name)
    page.add_node(placeholder)
    build_semantic_blocks(document)
    recover_canva_image_placeholders(document)
    slot = next(iter(page.slots.values()))
    image = page.node(slot.node_by_role["image"])
    assert image is not None
    before = {node.id: deepcopy(node.transform) for node in page.nodes.values()}
    document.metadata["products"] = [
        {
            "id": "p1",
            "display_name": "CARNE DE SERENO PREMIUM",
            "price": "45,99",
            "unit": "KG",
            "image_path": "/tmp/carne-sereno.png",
        }
    ]
    router = GraphicsCommandRouter(GraphicsSession(document))

    result = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product_id": "p1"})

    assert result.ok and result.changed
    assert page.node(name.id).text == "CARNE DE SERENO PREMIUM"
    assert page.node(whole.id).text == "45"
    assert page.node(cents.id).text == ",99"
    assert page.node(unit.id).text == "/KG"
    assert image.visible is True
    assert image.metadata["bound_image_source"] == "/tmp/carne-sereno.png"
    for node_id, transform in before.items():
        assert page.node(node_id).transform == transform


def test_placeholder_recovery_is_idempotent_and_does_not_duplicate_synthetic_nodes():
    document = GraphicsDocument(name="Idempotência placeholder")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    name = _text("Name", "PONTA DE PICANHA NELORE", 728, 801, 230, 30)
    placeholder = GraphicsNode(
        kind=NodeKind.RECT,
        name="Freeform 59",
        locked=True,
        transform=Transform(x=727.5, y=831.8, width=230.6, height=195),
        style={"fill": "#FFFFFF"},
    )
    _price(page, "Picanha", 881.6, 945.1, "44", ",63")
    page.add_node(name)
    page.add_node(placeholder)
    build_semantic_blocks(document)

    first = recover_canva_image_placeholders(document)
    first_nodes = set(page.nodes)
    first_slot = next(iter(page.slots.values()))
    first_image_id = first_slot.node_by_role["image"]
    second = recover_canva_image_placeholders(document)

    assert first.synthetic_image_slots == 1
    assert second.synthetic_image_slots == 0
    assert set(page.nodes) == first_nodes
    assert next(iter(page.slots.values())).node_by_role["image"] == first_image_id
