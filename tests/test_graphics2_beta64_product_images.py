"""Regression contracts for Beta64's product list, exclusive pages and packshots."""
from __future__ import annotations

from PIL import Image, ImageDraw
import pytest

from srstudio.graphics2.auto_promotion import propose_promotion
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.image_autofit import visible_product_crop
from srstudio.graphics2.item_slots import bind_product_to_item_slot, create_item_slot
from srstudio.graphics2.model import BindingRole, GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession


def product(code: str, image_path: str = "") -> dict:
    return {"id": code, "code": code, "name": f"PRODUTO {code}",
            "unit": "KG", "price": "12,99", "image_path": image_path}


def test_exclusion_is_project_scoped_and_does_not_destroy_catalog():
    session = GraphicsSession(GraphicsDocument())
    session.document.metadata["products"] = [product("A"), product("B"), product("C")]
    router = GraphicsCommandRouter(session)
    command = {"name": "set_product_active", "product_id": "B", "active": False}
    assert router.dispatch(command).ok
    assert router.payload()["editor"]["inactive_product_codes"] == ["B"]
    preview = router.dispatch({"name": "preview_auto_promotion"})
    assert preview.ok, preview.message
    assert preview.payload["total"] == 2
    ids = [code for p in preview.payload["pages"] for code in p["product_ids"]]
    assert ids == ["A", "C"]
    assert [p["id"] for p in session.document.metadata["products"]] == ["A", "B", "C"]
    restored = GraphicsSession(GraphicsDocument.from_dict(session.document.to_dict()))
    assert GraphicsCommandRouter(restored).payload()["editor"]["inactive_product_codes"] == ["B"]
    assert router.dispatch({"name": "undo"}).ok
    assert router.payload()["editor"]["inactive_product_codes"] == []
    assert router.dispatch({"name": "redo"}).ok
    assert router.payload()["editor"]["inactive_product_codes"] == ["B"]
    assert router.dispatch({"name": "set_product_active", "product_id": "B", "active": True}).ok
    assert router.dispatch({"name": "preview_auto_promotion"}).payload["total"] == 3


def test_excluded_star_never_creates_its_page():
    proposal = propose_promotion([product("A"), product("B")], {"B"}, excluded_codes={"B"})
    assert proposal.as_dict()["total"] == 1
    assert [(p.featured, p.product_ids) for p in proposal.pages] == [(False, ("A",))]
    with pytest.raises(ValueError, match="Nenhum produto ativo"):
        propose_promotion([product("A")], {"A"}, excluded_codes={"A"})


def test_alpha_autofit_keeps_margin_and_does_not_modify_source(tmp_path):
    path = tmp_path / "transparent.png"
    image = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((135, 45, 265, 260), fill=(225, 24, 22, 255))
    image.save(path)
    original = path.read_bytes()
    crop = visible_product_crop(str(path))
    assert crop["l"] > .25 and crop["r"] > .25
    assert crop["t"] > .10 and crop["b"] > .06
    assert path.read_bytes() == original
    opaque = tmp_path / "opaque.jpg"
    Image.new("RGB", (100, 150), "white").save(opaque)
    assert visible_product_crop(str(opaque)) == {}


def test_individual_starts_one_image_then_toggles_two_with_undo(tmp_path):
    path = tmp_path / "sample.png"
    picture = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    ImageDraw.Draw(picture).rectangle((85, 25, 215, 270), fill=(35, 80, 170, 255))
    picture.save(path)
    session = GraphicsSession(GraphicsDocument())
    slot = create_item_slot(session, "individual-beta44")
    assert bind_product_to_item_slot(session, slot.id, product("A", str(path)))
    primary = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    repeated = session.page.node(slot.metadata["image_repeat_node_id"])
    assert slot.metadata["image_count"] == 1
    assert repeated.visible is False
    assert primary.style.get("crop", {}).get("l", 0) > .1
    router = GraphicsCommandRouter(session)
    assert router.dispatch({"name": "set_product_image_count", "slot_id": slot.id, "count": 2}).ok
    assert repeated.visible
    assert router.dispatch({"name": "undo"}).ok
    restored_slot = session.page.slots[slot.id]
    assert session.page.node(restored_slot.metadata["image_repeat_node_id"]).visible is False
    assert router.dispatch({"name": "redo"}).ok
    restored_slot = session.page.slots[slot.id]
    assert session.page.node(restored_slot.metadata["image_repeat_node_id"]).visible


def test_qml_exposes_product_interactions():
    from pathlib import Path
    import srstudio.graphics2
    editor = Path(srstudio.graphics2.__file__).parent / "qml" / "GraphicsEditor.qml"
    qml = editor.read_text(encoding="utf-8")
    assert "set_product_active" in qml
    assert "set_product_image_count" in qml
    assert "auto_fit_product_image" in qml
    assert "onWheel: function(wheel)" in qml
    assert "zoomFromContain: true" in qml
    # Card controls must remain clickable above the drag hit area.
    assert "z: 1 // Keep +, − and ★ clickable above the row drag target." in qml


def test_legacy_duplicate_automatically_hides_without_losing_its_photo(tmp_path):
    path = tmp_path / "legacy.png"
    Image.new("RGBA", (80, 80), (42, 150, 200, 255)).save(path)
    session = GraphicsSession(GraphicsDocument())
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, product("LEGACY", str(path)))
    duplicate = session.page.node(slot.metadata["image_repeat_node_id"])
    # Simulates a saved Beta63 project with two visible images and no count flag.
    duplicate.visible = True
    slot.metadata.pop("image_count", None)
    reopened = GraphicsSession(GraphicsDocument.from_dict(session.document.to_dict()))
    router = GraphicsCommandRouter(reopened)
    old = reopened.page.slots[slot.id]
    repeated = reopened.page.node(old.metadata["image_repeat_node_id"])
    assert not repeated.visible and repeated.asset_id
    assert old.metadata["image_count"] == 1
    assert router.dispatch({"name": "set_product_image_count", "slot_id":slot.id, "count":2}).ok
    assert repeated.visible
    assert router.dispatch({"name":"set_item_price_mode", "slot_id":slot.id, "mode":"one"}).ok
    assert repeated.visible
    assert router.dispatch({"name":"set_item_price_mode", "slot_id":slot.id, "mode":"two"}).ok
    assert repeated.visible
