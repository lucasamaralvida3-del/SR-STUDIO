from __future__ import annotations

import json

import pytest

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, register_local_asset, save_package
from srstudio.graphics2.preflight import assert_document_integrity
from srstudio.graphics2.semantic_blocks import build_semantic_blocks


def _page(index: int, *, nodes: int = 20) -> GraphicsPage:
    page = GraphicsPage(name=f"QA Página {index + 1}", width=1080, height=1350)
    for node_index in range(nodes):
        column = node_index % 4
        row = node_index // 4
        page.add_node(
            GraphicsNode(
                kind=NodeKind.TEXT if node_index % 2 else NodeKind.RECT,
                name=f"Objeto {index + 1}-{node_index + 1}",
                text=f"QA {index + 1}/{node_index + 1}" if node_index % 2 else "",
                transform=Transform(
                    x=30 + column * 250,
                    y=40 + row * 120,
                    width=210,
                    height=80,
                ),
                style={"font_family": "Arial", "font_size": 20, "fill": "#F5F5F5"},
                z_index=node_index,
            )
        )
    return page


def _document(page_count: int, *, nodes_per_page: int = 20) -> GraphicsDocument:
    pages = [_page(index, nodes=nodes_per_page) for index in range(page_count)]
    document = GraphicsDocument(
        name=f"QA stress {page_count} páginas",
        pages=pages,
        active_page_id=pages[0].id,
    )
    document.metadata["qa_marker"] = {"pages": page_count, "nodes_per_page": nodes_per_page}
    return document


def _canonical(document: GraphicsDocument) -> str:
    return json.dumps(document.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _locked_text(name: str, text: str, x: float, y: float, width: float, height: float) -> GraphicsNode:
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=name,
        text=text,
        locked=True,
        transform=Transform(x=x, y=y, width=width, height=height),
        style={"font_family": "Arial", "font_size": 24},
        metadata={"source_name": name},
    )


def _product_card_document(product_count: int) -> tuple[GraphicsDocument, str]:
    document = GraphicsDocument(name=f"QA ProductCards x{product_count}")
    page = document.active_page
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Group Product QA",
        transform=Transform(x=40, y=40, width=320, height=260),
        metadata={
            "source": "pptx-group",
            "source_name": "Group Product QA",
            "pptx_group_generated": True,
            "pptx_group_depth": 1,
        },
    )
    page.add_node(group)
    name = _locked_text("Product Name", "PRODUTO QA 00", 60, 55, 260, 45)
    currency = _locked_text("Currency", "R$", 160, 205, 38, 42)
    whole = _locked_text("Whole", "10", 198, 170, 90, 80)
    cents = _locked_text("Cents", ",00", 288, 175, 48, 38)
    unit = _locked_text("Unit", "UN", 288, 220, 48, 32)
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Picture 1",
        locked=True,
        transform=Transform(x=75, y=105, width=150, height=120),
        metadata={"source_name": "Picture 1"},
    )
    for node in (name, image, currency, whole, cents, unit):
        page.add_node(node, parent_id=group.id)

    document.metadata["products"] = [
        {
            "id": f"qa-product-{index:02d}",
            "display_name": f"PRODUTO QA {index:02d}",
            "price": f"{10 + index},{index % 100:02d}",
            "unit": "UN",
            "image_path": f"/tmp/qa-product-{index:02d}.png",
        }
        for index in range(product_count)
    ]
    return document, name.id


@pytest.mark.parametrize("page_count", [10, 25, 50])
def test_large_documents_roundtrip_without_semantic_drift(tmp_path, page_count):
    document = _document(page_count)
    assert_document_integrity(document)
    expected = _canonical(document)

    path = tmp_path / f"qa-{page_count}.srscene"
    save_package(document, path, embed_local_assets=True)
    reopened = load_package(path, extract_assets_to=tmp_path / f"assets-{page_count}")

    assert_document_integrity(reopened)
    assert _canonical(reopened) == expected
    assert len(reopened.pages) == page_count
    assert sum(len(page.nodes) for page in reopened.pages) == page_count * 20


def test_repeated_25_page_save_load_is_stable_for_20_cycles(tmp_path):
    document = _document(25, nodes_per_page=12)
    expected = _canonical(document)
    current = document

    for cycle in range(20):
        path = tmp_path / f"cycle-{cycle:02d}.srscene"
        save_package(current, path, embed_local_assets=True)
        current = load_package(path, extract_assets_to=tmp_path / f"assets-{cycle:02d}")
        assert_document_integrity(current)
        assert _canonical(current) == expected


def test_undo_redo_move_loop_returns_to_exact_geometry():
    document = _document(1, nodes_per_page=1)
    node_id = next(iter(document.active_page.nodes))
    router = GraphicsCommandRouter(GraphicsSession(document))
    original = router.session.page.node(node_id).transform
    original_xy = (original.x, original.y)

    for _ in range(100):
        selected = router.dispatch({"name": "select", "node_id": node_id})
        assert selected.ok
        moved = router.dispatch({"name": "move", "dx": 3.0, "dy": -2.0, "snap": False})
        assert moved.ok and moved.changed
        undone = router.dispatch({"name": "undo"})
        assert undone.ok and undone.changed
        redone = router.dispatch({"name": "redo"})
        assert redone.ok and redone.changed
        undone_again = router.dispatch({"name": "undo"})
        assert undone_again.ok and undone_again.changed

    final = router.session.page.node(node_id).transform
    assert (final.x, final.y) == pytest.approx(original_xy)
    assert_document_integrity(router.session.document)


def test_thirty_one_product_cards_keep_bindings_isolated_and_roundtrip(tmp_path):
    product_count = 31
    document, original_name_id = _product_card_document(product_count)
    build_semantic_blocks(document)
    router = GraphicsCommandRouter(GraphicsSession(document))
    page = router.session.page
    assert len(page.slots) == 1
    original_slot_id = next(iter(page.slots))

    first_bind = router.dispatch(
        {"name": "bind_product", "slot_id": original_slot_id, "product_id": "qa-product-00"}
    )
    assert first_bind.ok and first_bind.changed
    slot_ids = [original_slot_id]

    for index in range(1, product_count):
        selected = router.dispatch(
            {"name": "select", "node_id": original_name_id, "semantic": True, "semantic_scope": "card"}
        )
        assert selected.ok
        duplicated = router.dispatch(
            {"name": "duplicate", "dx": 360 * (index % 3), "dy": 280 * (index // 3)}
        )
        assert duplicated.ok and duplicated.changed
        assert len(duplicated.payload["slot_ids"]) == 1
        clone_slot_id = duplicated.payload["slot_ids"][0]
        slot_ids.append(clone_slot_id)
        bound = router.dispatch(
            {"name": "bind_product", "slot_id": clone_slot_id, "product_id": f"qa-product-{index:02d}"}
        )
        assert bound.ok and bound.changed

    page = router.session.page
    assert len(slot_ids) == product_count
    assert len(set(slot_ids)) == product_count
    assert len(page.slots) == product_count
    bound_name_ids: set[str] = set()
    for index, slot_id in enumerate(slot_ids):
        slot = page.slots[slot_id]
        assert slot.product_id == f"qa-product-{index:02d}"
        name_id = slot.node_by_role[BindingRole.NAME.value]
        assert name_id not in bound_name_ids
        bound_name_ids.add(name_id)
        assert page.node(name_id).text == f"PRODUTO QA {index:02d}"

    assert_document_integrity(router.session.document)
    expected = _canonical(router.session.document)
    path = tmp_path / "qa-product-cards-31.srscene"
    save_package(router.session.document, path, embed_local_assets=True)
    reopened = load_package(path, extract_assets_to=tmp_path / "product-assets")
    assert_document_integrity(reopened)
    assert _canonical(reopened) == expected
    assert len(reopened.active_page.slots) == product_count


def test_forty_real_images_embed_extract_and_keep_node_asset_identity(tmp_path):
    pil_image = pytest.importorskip("PIL.Image")
    pages = [GraphicsPage(name=f"Imagens {index + 1}", width=1080, height=1350) for index in range(4)]
    document = GraphicsDocument(name="QA 40 imagens reais", pages=pages, active_page_id=pages[0].id)
    original_asset_ids: list[str] = []
    original_node_asset_ids: dict[str, str] = {}

    for index in range(40):
        source = tmp_path / "source-images" / f"image-{index:02d}.png"
        source.parent.mkdir(parents=True, exist_ok=True)
        rgb = ((index * 47) % 256, (index * 83) % 256, (index * 131) % 256)
        pil_image.new("RGB", (128, 128), rgb).save(source, format="PNG")
        asset = register_local_asset(document, source, mime="image/png")
        asset.width = 128
        asset.height = 128
        original_asset_ids.append(asset.id)

        page = pages[index // 10]
        local_index = index % 10
        column = local_index % 5
        row = local_index // 5
        node = GraphicsNode(
            kind=NodeKind.IMAGE,
            name=f"Imagem QA {index:02d}",
            asset_id=asset.id,
            transform=Transform(x=35 + column * 205, y=80 + row * 330, width=175, height=260),
            style={"fit": "cover", "focus_x": 0.5, "focus_y": 0.5, "zoom": 1.0},
            z_index=local_index,
        )
        page.add_node(node)
        original_node_asset_ids[node.id] = asset.id

    assert_document_integrity(document)
    package = tmp_path / "forty-images.srscene"
    save_package(document, package, embed_local_assets=True)
    reopened = load_package(package, extract_assets_to=tmp_path / "extracted-images")

    assert_document_integrity(reopened)
    assert len(reopened.pages) == 4
    assert len(reopened.assets) == 40
    assert set(reopened.assets) == set(original_asset_ids)
    assert sum(len(page.nodes) for page in reopened.pages) == 40
    for asset in reopened.assets.values():
        extracted = __import__("pathlib").Path(asset.source)
        assert asset.embedded is True
        assert asset.sha256
        assert extracted.is_file()
        assert extracted.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    for page in reopened.pages:
        for node in page.nodes.values():
            assert node.asset_id == original_node_asset_ids[node.id]
            assert node.metadata["package_asset_extracted"] is True
            assert node.metadata["bound_image_source"] == reopened.assets[node.asset_id].source
