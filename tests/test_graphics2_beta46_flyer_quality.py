from __future__ import annotations

import base64
from pathlib import Path

import pytest

from srstudio.graphics2.image_replace import replace_image_source
from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import bind_product_to_item_slot, create_item_slot
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.slot_export_audit import inspect_smart_slot_flyer


PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/kWQAAAAASUVORK5CYII="
)


def make_session():
    doc = GraphicsDocument(name="Encarte Beta46")
    doc.add_page(GraphicsPage(width=1080, height=1350))
    return GraphicsSession(doc)


@pytest.mark.parametrize("mode,count", [("individual",1),("six",6),("seven",7),("eleven",11)])
def test_complete_layout_is_exactly_one_undo_redo_step(mode, count):
    session = make_session()
    before = session.document.to_dict()
    command = ItemSlotCommandRouter(session)
    response = command.dispatch({"name":"apply_promotion_layout", "mode":mode})
    assert response.ok
    assert len(response.payload["slot_ids"]) == count
    after = session.document.to_dict()
    assert before != after
    assert session.history.undo_label == "Organizar layout com Smart Slots"
    assert session.undo()
    assert session.document.to_dict() == before
    assert not session.history.can_undo
    assert session.redo()
    assert session.document.to_dict() == after


def test_complex_layout_captures_history_only_once_not_per_slot(monkeypatch):
    session = make_session()
    router = ItemSlotCommandRouter(session)
    captures = []
    capture_original = session.history.capture

    def counted_capture(document):
        captures.append(1)
        return capture_original(document)

    monkeypatch.setattr(session.history, "capture", counted_capture)
    response = router.dispatch({"name":"apply_promotion_layout", "mode":"eleven"})
    assert response.ok
    assert len(response.payload["slot_ids"]) == 11
    # One before and one after, regardless of the number of slot/price
    # operations needed to assemble the design.
    assert len(captures) == 2
    assert session.history.can_undo


def test_nested_failure_rolls_back_whole_document_without_history_leak():
    session = make_session()
    before = session.document.to_dict()
    with pytest.raises(ValueError, match="Simulação"):
        with session.transaction("Criar layout"):
            create_item_slot(session, "individual-beta44")
            create_item_slot(session, "individual-beta44")
            raise ValueError("Simulação de falha no segundo slot")
    assert session.document.to_dict() == before
    assert not session.history.can_undo
    with session.transaction("Layout seguinte"):
        create_item_slot(session, "individual-beta44")
    assert session.history.undo_label == "Layout seguinte"


def test_replace_product_photo_centers_without_touching_price_or_position(tmp_path: Path):
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, {
        "id":"M1", "name":"ARROZ 5 KG", "price":"25,79"
    })
    page = session.page
    image = page.node(slot.node_by_role[BindingRole.IMAGE.value])
    image.style.update({"fit":"fill", "zoom":2.5, "focus_x":.1,
                        "focus_y":.9, "crop":{"l":.1, "r":.1}})
    rect = image.rect.normalized()
    initial_price = page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).text
    sample = tmp_path / "package.png"
    sample.write_bytes(PNG_1PX)
    result = replace_image_source(session, image.id, str(sample))
    assert result.node_id == image.id
    assert image.style["fit"] == "contain"
    assert image.style["zoom"] == 1.0
    assert image.style["focus_x"] == image.style["focus_y"] == .5
    assert "crop" not in image.style
    assert image.rect == rect
    assert page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).text == initial_price
    assert page.slots[slot.id].product_id == "M1"
    assert session.undo()
    image_recovered = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    assert image_recovered.style["fit"] == "fill"
    assert session.redo()
    assert session.page.node(slot.node_by_role[BindingRole.IMAGE.value]).style["fit"] == "contain"


def test_new_catalog_product_resets_only_image_crop_without_changing_price(tmp_path: Path):
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    image = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    image.style.update({"fit":"cover", "zoom":2.8, "crop":{"l":.3}})
    prior = image.rect.normalized()
    sample = tmp_path / "packaging.png"
    sample.write_bytes(PNG_1PX)
    bind_product_to_item_slot(session, slot.id, {
        "id":"SKU-ONE", "name":"CAFE 500 G", "price":"14,99",
        "image_path":str(sample)
    })
    assert image.style["fit"] == "contain"
    assert image.style["zoom"] == 1
    assert "crop" not in image.style
    assert image.rect == prior
    amount = session.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value])
    assert amount.text == "14"
    # Price-only updates of the same product retain the clean picture.
    bind_product_to_item_slot(session, slot.id, {
        "id":"SKU-ONE", "name":"CAFE 500 G", "price":"12,99"
    })
    assert amount.text == "12"
    assert image.visible and image.style["fit"] == "contain"


def test_generic_image_replacement_keeps_user_crop(tmp_path: Path):
    session = make_session()
    node = session.add_node(GraphicsNode(
        kind=NodeKind.IMAGE, name="foto livre",
        transform=Transform(x=100,y=100,width=240,height=150),
        style={"fit":"fill", "crop":{"l":.1}},
    ))
    sample = tmp_path / "generic.png"
    sample.write_bytes(PNG_1PX)
    replace_image_source(session, node.id, str(sample))
    assert node.style["fit"] == "fill"
    assert node.style["crop"] == {"l":.1}


def test_export_audit_detects_missing_product_photo_and_name_price_collision():
    session = make_session()
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, {
        "id":"MISSING", "name":"AMACIANTE 1L", "price":"9,99"
    })
    codes = {issue.code for issue in inspect_smart_slot_flyer(session.document)}
    assert "SLOT_IMAGE_MISSING" in codes
    name = session.page.node(slot.node_by_role[BindingRole.NAME.value])
    price = session.page.node(slot.metadata["role_area_nodes"]["price"])
    name.transform.x = price.rect.x + 2
    name.transform.y = price.rect.y + 2
    assert "SLOT_NAME_PRICE_OVERLAP" in {
        issue.code for issue in inspect_smart_slot_flyer(session.document)
    }


def test_export_audit_reports_out_of_page_and_does_not_change_document():
    session = make_session()
    response = ItemSlotCommandRouter(session).dispatch({
        "name":"apply_promotion_layout", "mode":"individual"
    })
    assert response.ok
    root = session.page.node(response.payload["root_node_ids"][0])
    root.transform.x = -100
    before = session.document.to_dict()
    codes = [issue.code for issue in inspect_smart_slot_flyer(session.document)]
    assert "SLOT_OUT_OF_PAGE" in codes
    assert session.document.to_dict() == before


def test_export_audit_detects_distortion_and_allows_valid_product_photo(tmp_path: Path):
    session = make_session()
    sample = tmp_path / "product.png"
    sample.write_bytes(PNG_1PX)
    slot = create_item_slot(session, "individual-beta44")
    bind_product_to_item_slot(session, slot.id, {
        "id":"TEST", "name":"CAFÉ 500G", "price":"7,99",
        "image_path":str(sample)
    })
    image = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    assert "SLOT_IMAGE_MISSING" not in {
        issue.code for issue in inspect_smart_slot_flyer(session.document)
    }
    image.style["fit"] = "fill"
    assert "SLOT_IMAGE_DISTORTION" in {
        issue.code for issue in inspect_smart_slot_flyer(session.document)
    }


def test_preview_cache_skips_all_rendering_on_second_request(tmp_path: Path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    from PySide6.QtGui import QGuiApplication
    from srstudio.graphics2.slot_preview import build_slot_preview_catalog
    import srstudio.graphics2.qt_renderer as renderer
    app = QGuiApplication.instance() or QGuiApplication([])
    first = build_slot_preview_catalog(tmp_path)
    def fail_if_called(*args, **kwargs):
        raise AssertionError("All thumbnails should be reused from cache")
    monkeypatch.setattr(renderer, "render_png", fail_if_called)
    second = build_slot_preview_catalog(tmp_path)
    assert second == first


def test_png_pdf_draw_same_canonical_price_card(tmp_path: Path, monkeypatch):
    pytest.importorskip("PySide6")
    pdfium = pytest.importorskip("pypdfium2")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QImage
    from srstudio.graphics2.qt_renderer import render_png, render_pdf
    app = QGuiApplication.instance() or QGuiApplication([])
    session = make_session()
    slot = create_item_slot(session, "individual-beta44", x=280, y=280)
    bind_product_to_item_slot(session, slot.id, {
        "id":"TEST", "name":"ARROZ BRANCO 5KG", "price":"29,90"
    })
    png = tmp_path / "preview.png"
    pdf = tmp_path / "preview.pdf"
    render_png(session.document, png,
               page_index=session.document.pages.index(session.page), target_width=540)
    render_pdf(session.document, pdf,
               page_indices=[session.document.pages.index(session.page)])
    raster_png = QImage(str(png))
    pdf_doc = pdfium.PdfDocument(str(pdf))
    raster_pdf = pdf_doc[0].render(scale=1.8).to_pil().convert("RGB")
    assert not raster_png.isNull()
    assert raster_pdf.width > 200
    # Compare the same large solid-blue region of the source price plate.
    root = session.page.node(slot.metadata["root_node_id"])
    price = session.page.node(slot.metadata["role_area_nodes"]["price"]).rect
    points = [
        (price.x + .05 * price.width, price.y + f * price.height)
        for f in (.2,.3,.4,.5,.6)
    ]
    for x, y in points:
        a = raster_png.pixelColor(round(x / session.page.width * raster_png.width()),
                                  round(y / session.page.height * raster_png.height()))
        c = raster_pdf.getpixel((
            round(x / session.page.width * (raster_pdf.width - 1)),
            round(y / session.page.height * (raster_pdf.height - 1)),
        ))
        assert abs(a.red()-c[0]) < 70
        assert abs(a.green()-c[1]) < 70
        assert abs(a.blue()-c[2]) < 70
