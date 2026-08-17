from __future__ import annotations

from pathlib import Path

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, Transform, build_semantic_blocks
from srstudio.graphics2.qt_host import load_launch_context


_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODELS = _REPO_ROOT / "src" / "srstudio" / "assets" / "poster_templates" / "legacy" / "models"


def _text(name: str, text: str, *, x: float, y: float, width: float, height: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=False,
        visible=True,
        transform=Transform(x=x, y=y, width=width, height=height),
        metadata={"source": "pptx", "source_name": name},
    )


def _node_by_name(page, name: str):
    return next(node for node in page.nodes.values() if node.name == name)


def test_named_club_only_price_and_limit_form_one_editable_product_slot():
    document = GraphicsDocument(name="Clube exclusivo")
    page = document.active_page
    page.width = 1080
    page.height = 1350
    product = _text("SR_CLUBE_PRODUTO", "CAFÉ TESTE 500G", x=120, y=300, width=820, height=180)
    currency = _text("WordArt 6", "R$", x=55, y=650, width=120, height=70)
    club_price = _text("SR_CLUBE_PRECO", "19,90", x=210, y=620, width=700, height=200)
    limit = _text("SR_CLUBE_LIMITE", "LIMITE DE 6UN POR CPF", x=150, y=900, width=760, height=80)
    for node in (product, currency, club_price, limit):
        page.add_node(node)

    report = build_semantic_blocks(document)

    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.metadata["explicit_named_semantics"] is True
    assert slot.node_by_role["name"] == product.id
    assert slot.node_by_role["limit"] == limit.id
    assert "price_complete" not in slot.node_by_role
    assert slot.metadata["extra_bindings"]["app_price_complete"] == [club_price.id]
    assert slot.metadata["extra_bindings"]["app_price_currency"] == [currency.id]
    assert report.price_blocks == 0
    assert report.app_price_blocks == 1
    assert report.product_cards == 1

    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    result = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot.id,
            "product": {
                "id": "club-001",
                "name": "CAFÉ NOVO 500G",
                "price": "21.90",
                "app_price": "17.49",
                "unit": "UN",
                "limit": "4UN",
            },
        }
    )
    assert result.ok is True and result.changed is True
    assert product.text == "CAFÉ NOVO 500G"
    assert club_price.text == "17,49"
    assert currency.text == "R$"
    assert limit.text == "LIMITE DE 4UN POR CPF"
    assert limit.visible is True

    assert session.undo() is True
    assert session.page.node(club_price.id).text == "19,90"
    assert session.page.node(limit.id).text == "LIMITE DE 6UN POR CPF"
    assert session.redo() is True
    assert session.page.node(club_price.id).text == "17,49"
    assert session.page.node(limit.id).text == "LIMITE DE 4UN POR CPF"


def test_real_clube_exclusivo_com_limite_uses_named_app_price_and_limit_binding():
    source = _MODELS / "CLUBE_EXCLUSIVO_COM_LIMITE.pptx"
    context = load_launch_context(source)
    session = GraphicsSession(context.document)
    page = session.page

    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.metadata.get("explicit_named_semantics") is True
    assert page.node(slot.node_by_role["name"]).name == "SR_CLUBE_PRODUTO"
    assert page.node(slot.node_by_role["limit"]).name == "SR_CLUBE_LIMITE"
    extra = dict(slot.metadata.get("extra_bindings") or {})
    assert page.node(extra["app_price_complete"][0]).name == "SR_CLUBE_PRECO"

    router = GraphicsCommandRouter(session)
    result = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot.id,
            "product": {
                "id": "real-club-001",
                "name": "LEITE TESTE 1L",
                "price": "5.99",
                "app_price": "4.79",
                "unit": "UN",
                "cpf_limit": "6UN",
            },
        }
    )
    assert result.ok is True and result.changed is True
    assert _node_by_name(session.page, "SR_CLUBE_PRODUTO").text == "LEITE TESTE 1L"
    assert _node_by_name(session.page, "SR_CLUBE_PRECO").text == "4,79"
    assert _node_by_name(session.page, "SR_CLUBE_LIMITE").text == "LIMITE DE 6UN POR CPF"
    assert _node_by_name(session.page, "SR_CLUBE_LIMITE").visible is True


def test_real_promotional_limit_field_is_part_of_named_slot_and_hides_when_empty():
    source = _MODELS / "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx"
    context = load_launch_context(source)
    session = GraphicsSession(context.document)
    page = session.page
    slot = next(iter(page.slots.values()))

    assert page.node(slot.node_by_role["limit"]).name == "SR_LIMITE"
    router = GraphicsCommandRouter(session)
    result = router.dispatch(
        {
            "name": "bind_product",
            "slot_id": slot.id,
            "product": {
                "id": "promo-no-limit",
                "name": "DETERGENTE TESTE 500ML",
                "price": "2.99",
                "unit": "UN",
                "limit": "",
            },
        }
    )
    assert result.ok is True and result.changed is True
    limit_node = _node_by_name(session.page, "SR_LIMITE")
    assert limit_node.text == ""
    assert limit_node.visible is False
