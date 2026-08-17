from __future__ import annotations

import os
from pathlib import Path

import pytest
from pypdf import PdfReader

from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.qt_renderer import render_pdf, render_png


def _text(name: str, text: str, x: float, y: float, width: float, height: float, size: float = 26) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        transform=Transform(x=x, y=y, width=width, height=height),
        style={"font_family": "Arial", "font_size": size, "font_size_unit": "px", "color": "#111111", "align": "center"},
    )


def _add_product_card(document: GraphicsDocument, index: int, x: float, y: float) -> tuple[str, str, dict[str, str]]:
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name=f"ProductCard {index + 1}",
        transform=Transform(x=x, y=y, width=300, height=250),
        z_index=100 + index * 10,
    )
    page.add_node(group)
    nodes = {
        "name": _text("Nome", f"PRODUTO {index + 1}", x + 15, y + 8, 270, 45, 18),
        "image": GraphicsNode(
            kind=NodeKind.IMAGE,
            name="Imagem",
            transform=Transform(x=x + 45, y=y + 55, width=150, height=120),
            style={"fit": "contain", "focus_x": 0.5, "focus_y": 0.5},
        ),
        "currency": _text("R$", "R$", x + 185, y + 155, 35, 35, 18),
        "price_reais": _text("Reais", "0", x + 215, y + 145, 55, 58, 36),
        "price_cents": _text("Centavos", ",00", x + 265, y + 148, 34, 28, 17),
        "unit": _text("Unidade", "/UN", x + 260, y + 180, 38, 24, 14),
        "limit": _text("Limite", "", x + 15, y + 205, 175, 30, 12),
        "app_price": _text("Clube", "", x + 190, y + 210, 108, 28, 12),
    }
    for node in nodes.values():
        page.add_node(node, parent_id=group.id)

    bindings = {
        BindingRole.NAME.value: nodes["name"].id,
        BindingRole.IMAGE.value: nodes["image"].id,
        BindingRole.CURRENCY.value: nodes["currency"].id,
        BindingRole.PRICE_REAIS.value: nodes["price_reais"].id,
        BindingRole.PRICE_CENTS.value: nodes["price_cents"].id,
        BindingRole.UNIT.value: nodes["unit"].id,
        BindingRole.LIMIT.value: nodes["limit"].id,
        BindingRole.APP_PRICE.value: nodes["app_price"].id,
    }
    slot = SmartSlot(name=f"Produto {index + 1}", page_id=page.id, node_by_role=bindings)
    page.slots[slot.id] = slot

    price_id = f"priceblock:{slot.id}:price"
    card_id = f"productcard:{slot.id}"
    price_roles = {
        BindingRole.CURRENCY.value: [nodes["currency"].id],
        BindingRole.PRICE_REAIS.value: [nodes["price_reais"].id],
        BindingRole.PRICE_CENTS.value: [nodes["price_cents"].id],
        BindingRole.UNIT.value: [nodes["unit"].id],
        BindingRole.APP_PRICE.value: [nodes["app_price"].id],
    }
    blocks = page.metadata.setdefault("semantic_blocks", {})
    blocks[price_id] = {
        "id": price_id,
        "kind": "price_block",
        "slot_id": slot.id,
        "members": [nodes[key].id for key in ("currency", "price_reais", "price_cents", "unit", "app_price")],
        "roles": price_roles,
        "metadata": {"smart_slot_id": slot.id},
    }
    blocks[card_id] = {
        "id": card_id,
        "kind": "product_card",
        "slot_id": slot.id,
        "members": [group.id],
        "roles": {
            BindingRole.NAME.value: [nodes["name"].id],
            BindingRole.IMAGE.value: [nodes["image"].id],
            BindingRole.LIMIT.value: [nodes["limit"].id],
        },
        "metadata": {
            "smart_slot_id": slot.id,
            "content_members": [node.id for node in nodes.values()],
            "price_blocks": [price_id],
            "name_node_id": nodes["name"].id,
            "image_node_id": nodes["image"].id,
        },
    }
    slot.metadata["semantic_product_card_id"] = card_id
    slot.metadata["semantic_price_block_ids"] = [price_id]
    for node in nodes.values():
        node.metadata["semantic_product_card_id"] = card_id
    for role, node_ids in price_roles.items():
        for node_id in node_ids:
            node = page.node(node_id)
            assert node is not None
            node.metadata["semantic_price_block_id"] = price_id
            node.metadata["semantic_price_role"] = role
    return group.id, slot.id, {key: node.id for key, node in nodes.items()}


def _products(image_paths: list[Path]) -> list[dict]:
    return [
        {
            "id": f"p{index:02d}",
            "display_name": f"PRODUTO SR {index:02d}",
            "price": f"{7 + index},{(13 * index) % 100:02d}",
            "unit": "KG" if index % 3 == 0 else "UN",
            "limit": f"{index % 6 + 1}UN" if index % 4 == 0 else "",
            "app_price": f"{6 + index},{(11 * index) % 100:02d}" if index % 2 == 0 else "",
            "image_path": str(image_paths[index]),
        }
        for index in range(len(image_paths))
    ]


def _assert_global_ids_unique(document: GraphicsDocument) -> None:
    page_ids = [page.id for page in document.pages]
    node_ids = [node_id for page in document.pages for node_id in page.nodes]
    slot_ids = [slot_id for page in document.pages for slot_id in page.slots]
    block_ids = [block_id for page in document.pages for block_id in (page.metadata.get("semantic_blocks") or {})]
    assert len(page_ids) == len(set(page_ids))
    assert len(node_ids) == len(set(node_ids))
    assert len(slot_ids) == len(set(slot_ids))
    assert len(block_ids) == len(set(block_ids))


def test_real_flyer_workflow_10_products_two_pages_roundtrip_recovery_and_exports(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QColor, QGuiApplication, QImage

    app = QGuiApplication.instance() or QGuiApplication([])
    image_paths: list[Path] = []
    for index in range(16):
        path = tmp_path / f"product-{index:02d}.png"
        image = QImage(64, 64, QImage.Format_ARGB32)
        image.fill(QColor.fromHsv((index * 23) % 360, 180, 220))
        assert image.save(str(path), "PNG")
        image_paths.append(path)

    document = GraphicsDocument(name="Encarte real E2E")
    page = document.active_page
    page.name = "Ofertas 1"
    page.width = 1080
    page.height = 1350
    page.add_node(_text("Cabeçalho", "OFERTAS SR", 80, 25, 920, 70, 42))
    page.add_node(_text("Rodapé", "OFERTAS VÁLIDAS ENQUANTO DURAREM OS ESTOQUES", 80, 1310, 920, 28, 14))
    page.add_node(_text("Validade", "VALIDADE: 17 A 20/08/2026", 330, 95, 420, 32, 16))

    cards: list[tuple[str, str, dict[str, str]]] = []
    for index in range(10):
        col = index % 3
        row = index // 3
        cards.append(_add_product_card(document, index, 45 + col * 340, 145 + row * 285))

    products = _products(image_paths)
    document.metadata["products"] = products
    router = GraphicsCommandRouter(GraphicsSession(document))

    # 8–12 produtos preenchidos semanticamente.
    for index, (_, slot_id, _) in enumerate(cards):
        result = router.dispatch({"name": "bind_product", "slot_id": slot_id, "product": products[index]})
        assert result.ok and result.changed
    assert len(router.session.page.slots) == 10

    # Substituir 3 produtos, incluindo imagem, preço, unidade, limite e preço clube.
    original_images = [router.session.page.node(cards[index][2]["image"]).metadata["bound_image_source"] for index in range(3)]
    for card_index, product_index in zip((0, 1, 2), (10, 11, 12)):
        slot_id = cards[card_index][1]
        result = router.dispatch({"name": "bind_product", "slot_id": slot_id, "product": products[product_index]})
        assert result.ok and result.changed
    for index in range(2):
        current = router.session.page.node(cards[index][2]["image"]).metadata["bound_image_source"]
        assert current != original_images[index]

    # Editar 3 nomes e 3 preços manualmente.
    for index in (3, 4, 5):
        ids = cards[index][2]
        assert router.dispatch({"name": "edit_text", "node_id": ids["name"], "text": f"NOME EDITADO {index}"}).changed
        assert router.dispatch({"name": "edit_text", "node_id": ids["price_reais"], "text": str(30 + index)}).changed
        assert router.dispatch({"name": "edit_text", "node_id": ids["price_cents"], "text": f",{70 + index}"}).changed

    # Mover e redimensionar cards sem quebrar a árvore interna.
    for index, delta in ((6, (15.0, 12.0)), (7, (-8.0, 18.0))):
        group_id, _, ids = cards[index]
        before = router.session.page.node(group_id).transform
        old_x, old_y = before.x, before.y
        router.dispatch({"name": "select", "node_id": ids["name"], "semantic": True, "semantic_scope": "card"})
        assert router.dispatch({"name": "move", "dx": delta[0], "dy": delta[1], "snap": False}).changed
        after = router.session.page.node(group_id).transform
        assert after.x == pytest.approx(old_x + delta[0])
        assert after.y == pytest.approx(old_y + delta[1])

    resize_group_id, _, resize_ids = cards[8]
    group = router.session.page.node(resize_group_id)
    child = router.session.page.node(resize_ids["image"])
    old_group_width, old_group_height = group.transform.width, group.transform.height
    old_child_width, old_child_height = child.transform.width, child.transform.height
    resized = router.dispatch({
        "name": "resize",
        "node_id": resize_group_id,
        "width": old_group_width * 0.9,
        "height": old_group_height * 0.9,
    })
    assert resized.ok and resized.changed
    assert router.session.page.node(resize_ids["image"]).transform.width == pytest.approx(old_child_width * 0.9)
    assert router.session.page.node(resize_ids["image"]).transform.height == pytest.approx(old_child_height * 0.9)

    # Duplicar card, excluir, undo e redo como operações atômicas.
    group_id, _, ids = cards[9]
    router.dispatch({"name": "select", "node_id": ids["name"], "semantic": True, "semantic_scope": "card"})
    duplicated = router.dispatch({"name": "duplicate", "dx": 25, "dy": -20})
    assert duplicated.changed and duplicated.payload["slot_ids"]
    clone_group_id = duplicated.payload["node_ids"][0]
    clone_slot_id = duplicated.payload["slot_ids"][0]
    assert clone_slot_id in router.session.page.slots
    router.dispatch({"name": "select", "node_id": clone_group_id, "semantic": True, "semantic_scope": "card"})
    assert router.dispatch({"name": "delete"}).changed
    assert clone_group_id not in router.session.page.nodes
    assert clone_slot_id not in router.session.page.slots
    assert router.dispatch({"name": "undo"}).changed
    assert clone_group_id in router.session.page.nodes
    assert clone_slot_id in router.session.page.slots
    assert router.dispatch({"name": "redo"}).changed
    assert clone_group_id not in router.session.page.nodes

    # Z-order real em card existente.
    layer_group_id, _, layer_ids = cards[0]
    router.dispatch({"name": "select", "node_id": layer_ids["name"], "semantic": True, "semantic_scope": "card"})
    assert router.dispatch({"name": "layer", "mode": "front"}).changed
    layer_tree = [layer_group_id, *router.session.page.descendants(layer_group_id)]
    assert min(router.session.page.node(node_id).z_index for node_id in layer_tree) >= 0

    # Segunda página duplicada com IDs independentes, depois modificada.
    first_page_id = router.session.page.id
    duplicated_page = router.dispatch({"name": "duplicate_page", "name_value": "Ofertas 2"})
    assert duplicated_page.changed
    assert len(router.session.document.pages) == 2
    second_page = router.session.page
    assert second_page.id != first_page_id
    _assert_global_ids_unique(router.session.document)
    second_slot_id = next(iter(second_page.slots))
    assert router.dispatch({"name": "bind_product", "slot_id": second_slot_id, "product": products[13]}).changed
    second_card_id = second_page.slots[second_slot_id].metadata["semantic_product_card_id"]
    second_group_id = second_page.metadata["semantic_blocks"][second_card_id]["members"][0]
    router.dispatch({"name": "select", "node_id": second_group_id, "semantic": True, "semantic_scope": "card"})
    assert router.dispatch({"name": "move", "dx": 12, "dy": 8, "snap": False}).changed

    # Save -> close -> reopen deve preservar duas páginas, semântica e edições.
    project = tmp_path / "encarte-e2e.srscene"
    save_package(router.session.document, project, embed_local_assets=True)
    reopened = load_package(project, extract_assets_to=tmp_path / "opened-assets")
    assert len(reopened.pages) == 2
    _assert_global_ids_unique(reopened)
    assert reopened.pages[1].slots[second_slot_id].product_id == products[13]["id"]
    assert any(node.text == "NOME EDITADO 3" for node in reopened.pages[0].nodes.values())
    assert any(node.text == "33" for node in reopened.pages[0].nodes.values())

    # Autosave/recovery preserva o último estado salvo e não usa o documento mutado depois.
    autosave = AutosaveManager(tmp_path / "autosave", generations=3, embed_local_assets=True)
    reopened.metadata["recovery_revision"] = "safe"
    autosave.save(reopened)
    reopened.metadata["recovery_revision"] = "dirty-after-crash"
    point = autosave.latest(reopened.id)
    assert point is not None
    recovered = autosave.recover(point, extract_assets_to=tmp_path / "recovered-assets")
    assert recovered.metadata["recovery_revision"] == "safe"
    assert len(recovered.pages) == 2
    _assert_global_ids_unique(recovered)

    # Export PNG + PDF multipágina, abrindo os dois resultados.
    png_path = tmp_path / "encarte-page1.png"
    png_report = render_png(recovered, png_path, page_index=0, dpi=96)
    assert png_report.ok
    assert png_report.width == 1080
    assert png_report.height == 1350
    exported_png = QImage(str(png_path))
    assert not exported_png.isNull()
    assert exported_png.width() == png_report.width
    assert exported_png.height() == png_report.height

    pdf_path = tmp_path / "encarte.pdf"
    pdf_report = render_pdf(recovered, pdf_path, dpi=300)
    assert pdf_report.ok
    assert pdf_report.pages == 2
    assert len(PdfReader(str(pdf_path)).pages) == 2
    app.processEvents()
