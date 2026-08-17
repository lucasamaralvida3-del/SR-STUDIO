from __future__ import annotations

import json

from srstudio.graphics2.model import (
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    GraphicsPage,
    NodeKind,
    SmartSlot,
    Transform,
)
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity


def _semantic_page(name: str, offset: int) -> GraphicsPage:
    page = GraphicsPage(name=name, width=1080, height=1350)
    name_node = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        text=f"PRODUTO {offset}",
        transform=Transform(x=80, y=120, width=420, height=60),
        style={"font_family": "Arial", "font_size": 30},
    )
    image_node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem",
        transform=Transform(x=90, y=210, width=260, height=250),
        style={"fit": "contain"},
    )
    reais = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Reais",
        text=str(10 + offset),
        transform=Transform(x=400, y=300, width=150, height=120),
    )
    cents = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Centavos",
        text=",99",
        transform=Transform(x=550, y=310, width=70, height=60),
    )
    unit = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Unidade",
        text="/UN",
        transform=Transform(x=550, y=370, width=70, height=40),
    )
    limit = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Limite",
        text="LIMITE DE 4UN POR CPF",
        transform=Transform(x=390, y=440, width=250, height=40),
    )
    for node in (name_node, image_node, reais, cents, unit, limit):
        page.add_node(node)

    slot = SmartSlot(
        name=f"Produto {offset}",
        page_id=page.id,
        product_id=f"p-{offset}",
        node_by_role={
            BindingRole.NAME.value: name_node.id,
            BindingRole.IMAGE.value: image_node.id,
            BindingRole.PRICE_REAIS.value: reais.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
            BindingRole.LIMIT.value: limit.id,
        },
        metadata={"source": "canva-smart-slot", "product_snapshot": {"id": f"p-{offset}"}},
    )
    page.slots[slot.id] = slot
    price_id = f"priceblock:{slot.id}:price"
    card_id = f"productcard:{slot.id}"
    slot.metadata["semantic_price_block_ids"] = [price_id]
    slot.metadata["semantic_product_card_id"] = card_id
    page.metadata["semantic_blocks"] = {
        price_id: {
            "id": price_id,
            "kind": "price_block",
            "slot_id": slot.id,
            "members": [reais.id, cents.id, unit.id],
            "roles": {
                "reais": [reais.id],
                "cents": [cents.id],
                "unit": [unit.id],
            },
            "metadata": {"smart_slot_id": slot.id},
        },
        card_id: {
            "id": card_id,
            "kind": "product_card",
            "slot_id": slot.id,
            "members": [name_node.id, image_node.id, reais.id, cents.id, unit.id, limit.id],
            "roles": {
                BindingRole.NAME.value: [name_node.id],
                BindingRole.IMAGE.value: [image_node.id],
                BindingRole.LIMIT.value: [limit.id],
            },
            "metadata": {
                "smart_slot_id": slot.id,
                "content_members": [name_node.id, image_node.id, reais.id, cents.id, unit.id, limit.id],
                "price_blocks": [price_id],
                "recovered": True,
                "atomic": True,
            },
        },
    }
    for node in page.nodes.values():
        node.metadata["semantic_product_card_id"] = card_id
    return page


def _document() -> GraphicsDocument:
    pages = [_semantic_page(f"Página {index + 1}", index + 1) for index in range(3)]
    document = GraphicsDocument(name="Stress semantic roundtrip", pages=pages, active_page_id=pages[1].id)
    document.metadata["products"] = [
        {"id": f"p-{index}", "display_name": f"PRODUTO {index}", "price": f"{10 + index},99", "unit": "UN"}
        for index in range(1, 4)
    ]
    document.metadata["stress_marker"] = {"revision": 7, "nested": [1, 2, {"ok": True}]}
    return document


def _canonical(document: GraphicsDocument) -> str:
    return json.dumps(document.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_repeated_save_reopen_keeps_multipage_semantics_byte_stable(tmp_path):
    document = _document()
    assert_document_integrity(document)
    expected = _canonical(document)

    current = document
    for cycle in range(10):
        path = tmp_path / f"cycle-{cycle:02d}.srscene"
        save_package(current, path, embed_local_assets=True)
        reopened = load_package(path, extract_assets_to=tmp_path / f"assets-{cycle:02d}")
        assert_document_integrity(reopened)
        assert _canonical(reopened) == expected
        assert reopened.active_page_id == document.active_page_id
        assert len(reopened.pages) == 3
        assert sum(len(page.slots) for page in reopened.pages) == 3
        assert sum(len(page.metadata["semantic_blocks"]) for page in reopened.pages) == 6
        current = reopened


def test_invalid_srscene_is_rejected_without_mutating_last_good_document(tmp_path):
    good = _document()
    expected = _canonical(good)
    broken = tmp_path / "broken.srscene"
    broken.write_bytes(b"not-a-zip-and-not-a-scene")

    try:
        load_package(broken)
    except (ValueError, OSError, KeyError):
        pass
    else:
        raise AssertionError("Pacote inválido deveria ser rejeitado.")

    assert _canonical(good) == expected
    assert_document_integrity(good)
