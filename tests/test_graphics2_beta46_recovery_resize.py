from __future__ import annotations

import base64
from pathlib import Path

import pytest

from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.item_slots import bind_product_to_item_slot, create_item_slot, refresh_all_item_slots
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.multi_item_strip import create_multi_item_strip
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity


# A valid 1x1 pixel PNG. The real package must carry this byte-for-byte.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/kWQAAAAASUVORK5CYII="
)


def make_session() -> GraphicsSession:
    doc = GraphicsDocument(name="Campanha SR - recuperação")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


def image_node(session: GraphicsSession, slot_id: str):
    slot = session.page.slots[slot_id]
    return session.page.node(slot.node_by_role[BindingRole.IMAGE.value])


@pytest.mark.parametrize("count", [5, 6])
def test_autosave_recovery_contains_all_multi_product_images_prices_and_positions(tmp_path: Path, count: int):
    session = make_session()
    file = tmp_path / "imagem-produto.png"
    file.write_bytes(PNG_1PX)

    multi = create_multi_item_strip(session, count=count, x=20, y=610)
    for i, sid in enumerate(multi["slot_ids"]):
        assert bind_product_to_item_slot(session, sid, {
            "id": f"SKU-{i}", "name": f"PRODUTO {i} 500ML",
            "price": f"{12 + i},99", "club_price": f"{10 + i},49",
            "image_path": str(file),
        })
    assert len(session.document.assets) == 1, "Identical local image reused across all columns"

    root = session.page.node(multi["root_node_id"])
    old = root.rect.normalized()
    session.resize_node(root.id, x=34, y=530, width=old.width*.87, height=old.height*.87)
    after_resize = root.rect.normalized()
    assert after_resize.width == pytest.approx(old.width*.87)

    manager = AutosaveManager(tmp_path / "autosave", generations=3)
    saved = manager.save(session.document)
    file.unlink()  # Realistic crash recovery after original image was moved.
    point = manager.latest(session.document.id)
    assert point is not None and point.path == saved
    restored = manager.recover(point, extract_assets_to=tmp_path / "extracted")
    assert_document_integrity(restored)
    page = next(p for p in restored.pages if p.id == session.page.id)
    multi_root = page.node(multi["root_node_id"])
    assert multi_root.rect.width == pytest.approx(after_resize.width)
    assert multi_root.rect.y == pytest.approx(after_resize.y)
    assert len(multi_root.metadata["child_slot_ids"]) == count

    from hashlib import sha256
    for i, sid in enumerate(multi["slot_ids"]):
        slot = page.slots[sid]
        assert slot.product_id == f"SKU-{i}"
        assert slot.metadata["original_product_snapshot"]["price"] == f"{12+i},99"
        assert page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).text == str(10+i)
        image = page.node(slot.node_by_role[BindingRole.IMAGE.value])
        recovered_file = Path(str(image.metadata["bound_image_source"]))
        assert recovered_file.exists()
        assert sha256(recovered_file.read_bytes()).digest() == sha256(PNG_1PX).digest()
    assert len(restored.assets) == 1

    # On-open migration must not change the saved geometry or product bindings.
    refresh_all_item_slots(restored)
    assert page.node(multi["root_node_id"]).rect.width == pytest.approx(after_resize.width)
    assert set(page.slots) == set(multi["slot_ids"])


def test_manual_saved_individual_roundtrip_and_undo_resize(tmp_path: Path):
    session = make_session()
    file = tmp_path / "arroz.png"
    file.write_bytes(PNG_1PX)
    item = create_item_slot(session, "individual-beta44", x=200, y=450)
    assert bind_product_to_item_slot(session, item.id, {
        "id": "ARROZ", "name": "Arroz Branco 5KG", "price": "29,90",
        "image_path": str(file),
    })
    root = session.page.node(item.metadata["root_node_id"])
    initial = root.rect.normalized()
    session.resize_node(root.id, x=220, y=470,
                        width=initial.width*0.75, height=initial.height*0.75)
    assert session.undo()
    assert session.page.node(item.metadata["root_node_id"]).rect.width == pytest.approx(initial.width)
    assert session.redo()
    resized = session.page.node(item.metadata["root_node_id"]).rect.normalized()
    assert resized.width == pytest.approx(initial.width * 0.75)

    saved = tmp_path / "projeto.srscene"
    save_package(session.document, saved)
    reopened = load_package(saved, extract_assets_to=tmp_path / "images")
    actual = next(p for p in reopened.pages if p.id == session.page.id)
    assert actual.slots[item.id].product_id == "ARROZ"
    assert actual.node(item.metadata["root_node_id"]).rect.width == pytest.approx(resized.width)
    assert Path(actual.node(item.node_by_role[BindingRole.IMAGE.value]).metadata["bound_image_source"]).read_bytes() == PNG_1PX


def test_autosave_rejects_corrupt_latest_generation_without_losing_previous(tmp_path: Path):
    session = make_session()
    manager = AutosaveManager(tmp_path / "saves", generations=3)
    session.document.metadata["revision"] = "safe"
    original = manager.save(session.document)
    session.document.metadata["revision"] = "new"
    corrupt = manager.save(session.document)
    corrupt.write_bytes(b"truncated")
    latest = manager.latest(session.document.id)
    assert latest is not None
    assert latest.path == original
    assert manager.recover(latest).metadata["revision"] == "safe"
