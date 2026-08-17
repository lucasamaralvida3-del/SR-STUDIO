from __future__ import annotations

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.import_bridge import CanvaBindingService, GraphicsImportService, from_imported_project
from srstudio.graphics2.operations import GraphicsSession
from srstudio.importers.pipeline import ImportSummary


def test_canva_visual_elements_become_scene_nodes_with_smart_slot():
    product = Product(display_name="ACÉM BOVINO", price="33,64", unit="KG", cpf_limit="6UN")
    card = ProductCard(id="slot-card-1", product_id=product.id, locked=True, overrides={"recognition_confidence": 0.97})
    page = Page(width=1080, height=1350, cards=[card], elements=[
        {"type": "rect", "x": 100, "y": 100, "width": 300, "height": 260, "fill": "#FFFFFF", "outline": "#740000", "z_index": 1, "source": "pptx"},
        {"type": "text", "x": 110, "y": 110, "width": 280, "height": 45, "text": "ACÉM BOVINO", "font_name": "Anton", "source_font_name": "Anton", "font_size": 24, "fill": "#740000", "z_index": 3, "source": "pptx", "slot_id": card.id, "slot_role": "name"},
        {"type": "text", "x": 160, "y": 270, "width": 100, "height": 70, "text": "33", "font_name": "Anton", "font_size": 54, "fill": "#740000", "z_index": 5, "source": "pptx", "slot_id": card.id, "slot_role": "price_integer", "canva_no_wrap": True, "canva_fit_inside_box": True},
        {"type": "text", "x": 260, "y": 270, "width": 55, "height": 45, "text": ",64", "font_name": "Anton", "font_size": 28, "fill": "#740000", "z_index": 5, "source": "pptx", "slot_id": card.id, "slot_role": "price_cents"},
        {"type": "text", "x": 315, "y": 290, "width": 55, "height": 30, "text": "/KG", "font_name": "Anton", "font_size": 16, "fill": "#740000", "z_index": 5, "source": "pptx", "slot_id": card.id, "slot_role": "unit"},
        {"type": "image", "x": 135, "y": 155, "width": 220, "height": 110, "path": "C:/produtos/acem.png", "image_fit": "contain", "z_index": 2, "source": "pptx", "slot_id": card.id, "slot_role": "image"},
    ])
    project = StudioProject(name="Quinta Filé", products=[product], pages=[page], settings={"canva_native_visual": True, "canva_import_version": 7, "canva_rendering_version": 7})
    document = from_imported_project(project); scene_page = document.active_page
    assert len(scene_page.nodes) == 6; assert scene_page.slots[card.id].confidence == 0.97
    name_node = scene_page.node(scene_page.slots[card.id].node_by_role["name"]); assert name_node.style["font_family"] == "Anton"; assert name_node.locked is False
    static_rect = next(node for node in scene_page.nodes.values() if node.kind.value == "rect"); assert static_rect.locked is True
    assert document.metadata["products"][0]["display_name"] == "ACÉM BOVINO"


def test_canva_binding_updates_split_price_without_moving_geometry():
    product = Product(display_name="ACÉM BOVINO", price="33,64", unit="KG"); card = ProductCard(id="slot-1", product_id=product.id)
    page = Page(cards=[card], elements=[
        {"type": "text", "x": 10, "y": 10, "width": 100, "height": 30, "text": "OLD", "slot_id": card.id, "slot_role": "name"},
        {"type": "text", "x": 20, "y": 50, "width": 80, "height": 60, "text": "1", "slot_id": card.id, "slot_role": "price_integer"},
        {"type": "text", "x": 100, "y": 50, "width": 40, "height": 30, "text": ",00", "slot_id": card.id, "slot_role": "price_cents"},
    ])
    document = from_imported_project(StudioProject(products=[product], pages=[page])); session = GraphicsSession(document); slot = session.page.slots[card.id]
    integer = session.page.node(slot.node_by_role["price_reais"]); cents = session.page.node(slot.node_by_role["price_cents"]); before = (integer.transform.x, integer.transform.y, integer.transform.width, integer.transform.height)
    assert CanvaBindingService.bind(session, card.id, {"id": "new", "display_name": "COSTELA", "price": "128,79", "unit": "KG"})
    assert integer.text == "128"; assert cents.text == ",79"; assert (integer.transform.x, integer.transform.y, integer.transform.width, integer.transform.height) == before


def test_import_service_runs_complete_semantic_recovery_for_ungrouped_canva_placeholder(tmp_path):
    class FakePipeline:
        def import_file(self, path, project):
            project.pages = [
                Page(
                    width=1080,
                    height=1350,
                    elements=[
                        {"type": "text", "x": 20, "y": 458, "width": 345, "height": 44, "text": "ACÉM BOVINO", "font_name": "Anton", "font_size": 38, "source": "pptx"},
                        {"type": "rect", "x": 41, "y": 503, "width": 289, "height": 244, "fill": "#FFFFFF", "z_index": 10, "source": "pptx", "name": "Freeform 13"},
                        {"type": "text", "x": 233, "y": 676, "width": 39, "height": 48, "text": "R$", "font_name": "Anton", "font_size": 26, "source": "pptx"},
                        {"type": "text", "x": 278, "y": 646, "width": 98, "height": 116, "text": "33", "font_name": "Anton", "font_size": 82, "source": "pptx"},
                        {"type": "text", "x": 382, "y": 651, "width": 43, "height": 41, "text": ",64", "font_name": "Anton", "font_size": 30, "source": "pptx"},
                        {"type": "text", "x": 390, "y": 705, "width": 38, "height": 41, "text": "KG", "font_name": "Anton", "font_size": 26, "source": "pptx"},
                    ],
                )
            ]
            return ImportSummary(str(path))

    source = tmp_path / "fake.xlsx"
    source.write_bytes(b"fake")
    service = GraphicsImportService()
    service.pipeline = FakePipeline()

    result = service.import_file(source, project_name="Quinta Filé")

    page = result.document.active_page
    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    assert slot.name == "ACÉM BOVINO"
    assert set(slot.node_by_role) >= {"name", "image", "currency", "price_reais", "price_cents", "unit"}
    image = page.node(slot.node_by_role["image"])
    assert image is not None
    assert image.metadata["semantic_synthetic_image_slot"] is True
    assert image.visible is False
    recovery = result.document.metadata["semantic_recovery_complete"]
    assert recovery["ready"] is True
    assert recovery["slots"] == 1
    assert recovery["synthetic_image_slots"] == 1
