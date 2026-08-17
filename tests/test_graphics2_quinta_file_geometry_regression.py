from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.semantic_blocks import build_semantic_blocks
from srstudio.graphics2.semantic_recovery import recover_canva_semantic_cards


# Coordenadas normalizadas da página real do Canva/PPTX que originou o defeito
# de cards quebrados. Nenhuma imagem/arte proprietária é versionada aqui: apenas
# a geometria estrutural dos seis cards principais.
CARDS = [
    {
        "name": ("ACÉM BOVINO", 17.5, 458.2, 347.9, 44.4),
        "placeholder": (40.6, 502.6, 288.5, 243.9),
        "price": ((233.3, 676.2, 38.8, 48.4), (278.0, 645.6, 98.2, 115.6, "33"), (381.5, 651.3, 42.8, 41.4, ",64"), (389.6, 705.1, 37.9, 40.9)),
    },
    {
        "name": ("CARNE DE SERENO", 468.0, 557.4, 199.2, 49.5),
        "placeholder": (468.9, 583.5, 198.9, 168.1),
        "price": ((601.8, 702.4, 26.8, 34.1), (631.6, 682.2, 72.4, 79.5, "42"), (703.9, 686.0, 29.5, 28.6, ",66"), (707.1, 724.8, 29.1, 26.6)),
    },
    {
        "name": ("COXA E SOBRECOXA", 758.4, 553.0, 219.0, 52.0),
        "placeholder": (772.0, 581.0, 198.9, 168.1),
        "price": ((904.8, 699.9, 26.8, 34.1), (935.6, 679.7, 71.5, 79.5, "8"), (1007.0, 683.5, 29.5, 28.6, ",79"), (1012.6, 722.2, 22.4, 26.6)),
    },
    {
        "name": ("COSTELA RIPA", -44.4, 795.2, 390.3, 35.2),
        "placeholder": (38.4, 831.8, 230.6, 195.0),
        "price": ((192.4, 970.3, 31.0, 38.9), (224.0, 945.1, 82.9, 93.3, "24"), (310.9, 951.3, 34.2, 32.5, ",79"), (317.4, 995.1, 30.9, 31.3)),
    },
    {
        "name": ("BACON ADEEL TIPO 1", 322.4, 798.0, 351.8, 30.5),
        "placeholder": (383.0, 831.8, 230.6, 195.0),
        "price": ((537.0, 970.3, 31.0, 38.9), (568.4, 945.1, 86.8, 93.4, "31"), (652.0, 951.3, 46.6, 32.5, ",69"), (662.0, 995.1, 32.9, 31.3)),
    },
    {
        "name": ("PONTA DE PICANHA NELORE", 727.5, 801.4, 230.6, 26.1),
        "placeholder": (727.5, 831.8, 230.6, 195.0),
        "price": ((881.6, 970.3, 31.0, 38.9), (916.7, 945.1, 82.9, 93.4, "44"), (1000.2, 951.3, 33.9, 32.5, ",63"), (1006.5, 995.1, 25.9, 31.3)),
    },
]


def _text(label: str, text: str, x: float, y: float, w: float, h: float, size: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=label,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": size},
        metadata={"source_name": label},
    )


def _build_real_geometry_page() -> GraphicsDocument:
    document = GraphicsDocument(name="Quinta Filé — geometria real")
    page = document.active_page
    page.width = 1080.0
    page.height = 1350.0
    for index, card in enumerate(CARDS, start=1):
        name, x, y, w, h = card["name"]
        page.add_node(_text(f"Name {index}", name, x, y, w, h, 38))
        px, py, pw, ph = card["placeholder"]
        page.add_node(
            GraphicsNode(
                kind=NodeKind.RECT,
                name=f"White Placeholder {index}",
                locked=True,
                transform=Transform(x=px, y=py, width=pw, height=ph),
                z_index=index * 10,
                style={"fill": "#FFFFFF"},
                metadata={"source_name": f"White Placeholder {index}"},
            )
        )
        currency, whole, cents, unit = card["price"]
        page.add_node(_text(f"Currency {index}", "R$", *currency, 26))
        wx, wy, ww, wh, whole_text = whole
        page.add_node(_text(f"Whole {index}", whole_text, wx, wy, ww, wh, 82))
        cx, cy, cw, ch, cents_text = cents
        page.add_node(_text(f"Cents {index}", cents_text, cx, cy, cw, ch, 30))
        page.add_node(_text(f"Unit {index}", "KG", *unit, 26))
    return document


def test_quinta_file_real_geometry_recovers_six_distinct_cards_and_image_slots():
    document = _build_real_geometry_page()
    page = document.active_page

    semantic = build_semantic_blocks(document)
    slots_after_semantic = semantic.recovered_smart_slots
    recovery = recover_canva_semantic_cards(document)

    assert semantic.recovered_price_blocks == 6
    # A primeira passagem usa somente texto/geometria e pode deliberadamente
    # deixar casos ambíguos órfãos. O backplate branco é a segunda âncora forte.
    assert slots_after_semantic >= 3
    assert recovery.orphan_cards_promoted == 6 - slots_after_semantic
    assert recovery.synthetic_image_slots == 6
    assert len(page.slots) == 6
    slots_by_name = {slot.name: slot for slot in page.slots.values()}
    assert set(slots_by_name) == {card["name"][0] for card in CARDS}
    for card in CARDS:
        name = card["name"][0]
        slot = slots_by_name[name]
        assert slot.node_by_role.get("name")
        assert slot.node_by_role.get("image")
        assert slot.node_by_role.get("currency")
        assert slot.node_by_role.get("price_reais")
        assert slot.node_by_role.get("price_cents")
        assert slot.node_by_role.get("unit")
        image = page.node(slot.node_by_role["image"])
        assert image is not None and image.metadata["semantic_synthetic_image_slot"] is True
        assert image.visible is False


def test_quinta_file_real_geometry_does_not_cross_bind_neighbor_names_or_placeholders():
    document = _build_real_geometry_page()
    page = document.active_page
    build_semantic_blocks(document)
    recover_canva_semantic_cards(document)
    slots_by_name = {slot.name: slot for slot in page.slots.values()}

    for card in CARDS:
        name = card["name"][0]
        slot = slots_by_name[name]
        name_node = page.node(slot.node_by_role["name"])
        placeholder = page.node(slot.metadata["recovered_image_placeholder_id"])
        assert name_node is not None and name_node.text == name
        expected = card["placeholder"]
        assert placeholder is not None
        assert round(placeholder.transform.x, 1) == round(expected[0], 1)
        assert round(placeholder.transform.y, 1) == round(expected[1], 1)
