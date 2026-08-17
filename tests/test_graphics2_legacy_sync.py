from __future__ import annotations

from decimal import Decimal

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.compat import from_studio_project
from srstudio.graphics2.legacy_sync import fingerprint_studio_project, sync_graphics_to_studio
from srstudio.graphics2.model import BindingRole


def _project() -> StudioProject:
    product = Product(
        id="product-1",
        display_name="ACÉM BOVINO",
        price="25,77",
        unit="KG",
        image_path="C:/BancoSR/acem.png",
        metadata={"catalog_source": "SR"},
    )
    card = ProductCard(
        id="card-1",
        product_id=product.id,
        x=120,
        y=180,
        width=280,
        height=230,
        rotation=0,
        z_index=4,
    )
    page = Page(
        id="page-1",
        name="Página 1",
        width=1080,
        height=1350,
        background="#101010",
        cards=[card],
        elements=[{"type": "fixed-artwork", "keep": True}],
    )
    return StudioProject(
        id="project-1",
        name="Quinta Filé",
        campaign="QUINTA FILÉ",
        products=[product],
        pages=[page],
        settings={"legacy_only": {"keep": True}},
    )


def _slot_node(document, role: BindingRole):
    page = document.pages[0]
    slot = next(iter(page.slots.values()))
    return page.nodes[slot.node_by_role[role.value]]


def test_sync_projects_only_representable_product_and_card_fields_without_destroying_legacy_data():
    project = _project()
    document = from_studio_project(project)

    _slot_node(document, BindingRole.NAME).text = "ACÉM PREMIUM"
    _slot_node(document, BindingRole.PRICE_REAIS).text = "39"
    _slot_node(document, BindingRole.PRICE_CENTS).text = ",90"
    _slot_node(document, BindingRole.UNIT).text = "/KG"
    _slot_node(document, BindingRole.IMAGE).metadata["bound_image_source"] = "C:/BancoSR/acem-premium.png"

    group = document.pages[0].nodes["card-1"]
    group.transform.x = 222
    group.transform.y = 333
    group.transform.width = 300
    group.transform.height = 250
    group.transform.rotation = 7.5
    group.locked = True
    group.z_index = 9

    report = sync_graphics_to_studio(document, project)

    assert report.ok and not report.conflict
    assert report.products_updated == 1
    assert report.cards_updated == 1
    assert project.products[0].display_name == "ACÉM PREMIUM"
    assert project.products[0].price == Decimal("39.90")
    assert project.products[0].unit == "KG"
    assert project.products[0].image_path == "C:/BancoSR/acem-premium.png"
    assert project.pages[0].cards[0].x == 222
    assert project.pages[0].cards[0].y == 333
    assert project.pages[0].cards[0].width == 300
    assert project.pages[0].cards[0].height == 250
    assert project.pages[0].cards[0].rotation == 7.5
    assert project.pages[0].cards[0].locked is True
    assert project.pages[0].cards[0].z_index == 9
    assert project.pages[0].elements == [{"type": "fixed-artwork", "keep": True}]
    assert project.settings == {"legacy_only": {"keep": True}}
    assert document.metadata["legacy_source_fingerprint"] == fingerprint_studio_project(project)


def test_sync_refuses_to_overwrite_project_changed_after_engine_session_started():
    project = _project()
    document = from_studio_project(project)
    _slot_node(document, BindingRole.NAME).text = "NOME DO ENGINE 2"

    project.products[0].display_name = "ALTERAÇÃO MAIS NOVA NO STUDIO"
    report = sync_graphics_to_studio(document, project)

    assert not report.ok
    assert report.conflict
    assert project.products[0].display_name == "ALTERAÇÃO MAIS NOVA NO STUDIO"
    assert report.source_fingerprint != report.current_fingerprint


def test_render_metadata_is_ignored_by_legacy_conflict_fingerprint():
    project = _project()
    document = from_studio_project(project)
    initial = fingerprint_studio_project(project)

    project.products[0].metadata["render_state"] = "PRONTO"
    project.products[0].metadata["render_error"] = ""

    assert fingerprint_studio_project(project) == initial
    report = sync_graphics_to_studio(document, project)
    assert report.ok
    assert not report.conflict


def test_existing_pages_can_be_reordered_without_recreating_legacy_page_objects():
    project = _project()
    second = Page(id="page-2", name="Página 2", elements=[{"legacy": 2}])
    project.pages.append(second)
    document = from_studio_project(project)

    document.pages[:] = [document.pages[1], document.pages[0]]
    report = sync_graphics_to_studio(document, project)

    assert report.ok
    assert report.pages_reordered
    assert [page.id for page in project.pages] == ["page-2", "page-1"]
    assert project.pages[0] is second
    assert project.pages[0].elements == [{"legacy": 2}]
