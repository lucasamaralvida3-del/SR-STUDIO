from __future__ import annotations

from srstudio.graphics2.model import (
    AssetRef,
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    NodeKind,
    SmartSlot,
    Transform,
)
from srstudio.graphics2.slot_corpus_ground_truth import extract_slot_corpus_ground_truth


def _text(text: str, x: float, y: float, w: float, h: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        text=text,
        transform=Transform(x=x, y=y, width=w, height=h),
        style={"font_family": "Anton", "font_size": 28},
    )


def _add_real_product(
    document: GraphicsDocument,
    *,
    prefix: str,
    x: float,
    product_name: str,
    unit_text: str,
    promotion: bool = False,
    club: bool = False,
) -> SmartSlot:
    page = document.active_page
    card_x, card_y, card_w, card_h = x, 160.0, 280.0, 330.0

    asset = document.add_asset(
        AssetRef(
            id=f"asset-{prefix}",
            source=f"/corpus/{prefix}.png",
            sha256=(prefix * 64)[:64],
            width=600,
            height=600,
        )
    )
    image = GraphicsNode(
        id=f"image-{prefix}",
        kind=NodeKind.IMAGE,
        asset_id=asset.id,
        transform=Transform(x=card_x + 25, y=card_y + 50, width=190, height=155),
        style={"fit": "contain", "crop": {}},
    )
    name = _text(product_name, card_x + 18, card_y + 8, 235, 38)
    name.id = f"name-{prefix}"
    currency = _text("R$", card_x + 35, card_y + 235, 32, 42)
    currency.id = f"currency-{prefix}"
    integer = _text("24", card_x + 68, card_y + 218, 92, 76)
    integer.id = f"integer-{prefix}"
    decimal = _text(",79", card_x + 160, card_y + 223, 45, 35)
    decimal.id = f"decimal-{prefix}"
    unit = _text(unit_text, card_x + 165, card_y + 262, 62, 28)
    unit.id = f"unit-{prefix}"

    for node in (image, name, currency, integer, decimal, unit):
        page.add_node(node)

    extra_bindings: dict[str, list[str]] = {}
    content_members = [image.id, name.id, currency.id, integer.id, decimal.id, unit.id]
    if promotion:
        promo = _text("PROMOÇÃO", card_x + 215, card_y + 205, 58, 26)
        promo.id = f"promotion-{prefix}"
        page.add_node(promo)
        extra_bindings["promotion"] = [promo.id]
        content_members.append(promo.id)
    if club:
        club_node = _text("NO SR CLUBE SMART", card_x + 18, card_y + 296, 190, 25)
        club_node.id = f"club-{prefix}"
        page.add_node(club_node)
        extra_bindings["club_label"] = [club_node.id]
        content_members.append(club_node.id)

    slot = SmartSlot(
        id=f"slot-{prefix}",
        name=product_name,
        page_id=page.id,
        confidence=0.97,
        node_by_role={
            BindingRole.IMAGE.value: image.id,
            BindingRole.NAME.value: name.id,
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: integer.id,
            BindingRole.PRICE_CENTS.value: decimal.id,
            BindingRole.UNIT.value: unit.id,
        },
        metadata={
            "semantic_product_card_id": f"card-{prefix}",
            "semantic_price_block_ids": [f"price-{prefix}"],
            "extra_bindings": extra_bindings,
        },
    )
    page.slots[slot.id] = slot

    blocks = page.metadata.setdefault("semantic_blocks", {})
    blocks[f"price-{prefix}"] = {
        "id": f"price-{prefix}",
        "kind": "price_block",
        "slot_id": slot.id,
        "members": [currency.id, integer.id, decimal.id, unit.id],
        "roles": {
            "currency": [currency.id],
            "reais": [integer.id],
            "cents": [decimal.id],
            "unit": [unit.id],
        },
        "bounds": {
            "x": card_x + 35,
            "y": card_y + 218,
            "width": 192,
            "height": 72,
        },
        "metadata": {"complete": True},
    }
    blocks[f"card-{prefix}"] = {
        "id": f"card-{prefix}",
        "kind": "product_card",
        "slot_id": slot.id,
        "members": content_members,
        "roles": {
            BindingRole.IMAGE.value: [image.id],
            BindingRole.NAME.value: [name.id],
            BindingRole.UNIT.value: [unit.id],
            **extra_bindings,
        },
        "bounds": {"x": card_x, "y": card_y, "width": card_w, "height": card_h},
        "metadata": {
            "price_blocks": [f"price-{prefix}"],
            "content_members": content_members,
            "confidence": 0.97,
        },
    }
    return slot


def test_unit_wording_does_not_split_equivalent_structural_family() -> None:
    document = GraphicsDocument(name="Quinta Filé supervised corpus")
    page = document.active_page
    page.width = 1080
    page.height = 1350

    _add_real_product(document, prefix="a", x=40, product_name="MAÇÃ DO PEITO", unit_text="KG")
    _add_real_product(document, prefix="b", x=390, product_name="PERNIL SUÍNO", unit_text="CADA")
    _add_real_product(document, prefix="c", x=740, product_name="COSTELA RIPA", unit_text="QUILO")

    report = extract_slot_corpus_ground_truth(
        document,
        source_name="OFERTAS QUINTA FILÉ NOVO (3).pptx",
        source_sha256="f" * 64,
    )

    assert report["product_cards"] == 3
    assert report["slot_families"] == 1
    assert {example["family_id"] for example in report["examples"]} == {report["families"][0]["family_id"]}
    assert [example["expected_unit_bounds"]["texts"][0] for example in report["examples"]] == ["KG", "CADA", "QUILO"]
    assert all(example["expected_product_center"]["relative_x"] == 0.5 for example in report["examples"])
    assert all(example["expected_image_bounds"]["relative_bounds"] for example in report["examples"])
    assert all(example["expected_priceblock_bounds"]["node_ids"] for example in report["examples"])


def test_image_association_reuses_image_db_normalization_and_provenance() -> None:
    document = GraphicsDocument(name="Image ground truth")
    _add_real_product(
        document,
        prefix="d",
        x=100,
        product_name="Maçã do Peito 1KG",
        unit_text="KG",
    )

    report = extract_slot_corpus_ground_truth(
        document,
        source_name="OFERTAS QUINTA FILÉ NOVO (3).pptx",
        source_sha256="1" * 64,
    )

    association = report["product_image_associations"][0]
    assert association["product_name"] == "Maçã do Peito 1KG"
    assert association["normalized_name"] == "MACA DO PEITO 1KG"
    assert association["image_node_id"] == "image-d"
    assert association["asset_id"] == "asset-d"
    assert association["image_source"] == "/corpus/d.png"
    assert association["provenance"]["source_file"] == "OFERTAS QUINTA FILÉ NOVO (3).pptx"
    assert association["provenance"]["source_sha256"] == "1" * 64
    assert association["provenance"]["name_node_id"] == "name-d"


def test_promotion_and_club_are_independent_roles_not_name_content() -> None:
    document = GraphicsDocument(name="Promotion roles")
    _add_real_product(
        document,
        prefix="e",
        x=100,
        product_name="DETERGENTE SMART 500ML",
        unit_text="UN",
        promotion=True,
        club=True,
    )

    report = extract_slot_corpus_ground_truth(document)
    example = report["examples"][0]

    assert example["expected_name_bounds"]["texts"] == ["DETERGENTE SMART 500ML"]
    assert example["expected_promotion_bounds"]["texts"] == ["PROMOÇÃO"]
    assert example["expected_club_bounds"]["texts"] == ["NO SR CLUBE SMART"]
    assert example["family_signature"]["has_promotion"] is True
    assert example["family_signature"]["has_club"] is True
