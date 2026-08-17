from __future__ import annotations

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.legacy_sync import fingerprint_studio_project
from srstudio.graphics2.model import BindingRole
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.studio_bridge import prepare_studio_project, sync_saved_session_to_project


def _project() -> StudioProject:
    product = Product(id="p1", display_name="LINGUIÇA MISTA CASEIRA SR", price="25,77", unit="KG")
    card = ProductCard(id="c1", product_id=product.id, x=100, y=160, width=320, height=260)
    page = Page(id="pg1", name="Página principal", cards=[card])
    return StudioProject(id="quinta-file", name="Quinta Filé", products=[product], pages=[page])


def _edit_saved_session(package_path, tmp_path, *, name="LINGUIÇA PREMIUM", reais="31", cents=",45", x=222):
    document = load_package(package_path, extract_assets_to=tmp_path / "extract")
    page = document.pages[0]
    slot = next(iter(page.slots.values()))
    page.nodes[slot.node_by_role[BindingRole.NAME.value]].text = name
    page.nodes[slot.node_by_role[BindingRole.PRICE_REAIS.value]].text = reais
    page.nodes[slot.node_by_role[BindingRole.PRICE_CENTS.value]].text = cents
    page.nodes["c1"].transform.x = x
    save_package(document, package_path, embed_local_assets=True)


def test_prepare_reuses_existing_g2_session_when_legacy_project_did_not_change(tmp_path):
    project = _project()
    first = prepare_studio_project(project, tmp_path)
    assert not first.reused_session

    _edit_saved_session(first.package_path, tmp_path)
    second = prepare_studio_project(project, tmp_path)

    assert second.reused_session
    restored = load_package(second.package_path, extract_assets_to=tmp_path / "verify")
    page = restored.pages[0]
    slot = next(iter(page.slots.values()))
    assert page.nodes[slot.node_by_role[BindingRole.NAME.value]].text == "LINGUIÇA PREMIUM"
    assert page.nodes["c1"].transform.x == 222


def test_prepare_backs_up_old_g2_session_and_regenerates_when_legacy_project_changed(tmp_path):
    project = _project()
    first = prepare_studio_project(project, tmp_path)
    _edit_saved_session(first.package_path, tmp_path, name="EDIÇÃO SOMENTE G2")

    project.products[0].display_name = "ALTERAÇÃO NOVA NO STUDIO"
    second = prepare_studio_project(project, tmp_path)

    assert not second.reused_session
    assert second.previous_package_path is not None
    assert second.previous_package_path.is_file()

    previous = load_package(second.previous_package_path, extract_assets_to=tmp_path / "previous")
    previous_slot = next(iter(previous.pages[0].slots.values()))
    assert previous.pages[0].nodes[previous_slot.node_by_role[BindingRole.NAME.value]].text == "EDIÇÃO SOMENTE G2"

    regenerated = load_package(second.package_path, extract_assets_to=tmp_path / "new")
    new_slot = next(iter(regenerated.pages[0].slots.values()))
    assert regenerated.pages[0].nodes[new_slot.node_by_role[BindingRole.NAME.value]].text == "ALTERAÇÃO NOVA NO STUDIO"


def test_saved_g2_session_can_be_applied_selectively_back_to_studio_and_updates_baseline(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    _edit_saved_session(prepared.package_path, tmp_path, name="LINGUIÇA ARTESANAL", reais="29", cents=",99", x=245)

    result = sync_saved_session_to_project(project, tmp_path)

    assert result.ok
    assert result.report is not None
    assert project.products[0].display_name == "LINGUIÇA ARTESANAL"
    assert str(project.products[0].price) == "29.99"
    assert project.pages[0].cards[0].x == 245

    saved = load_package(prepared.package_path, extract_assets_to=tmp_path / "post-sync")
    assert saved.metadata["legacy_source_fingerprint"] == fingerprint_studio_project(project)
    assert saved.metadata["legacy_last_sync_fingerprint"] == fingerprint_studio_project(project)


def test_saved_g2_sync_is_blocked_when_studio_changed_after_session_creation(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    _edit_saved_session(prepared.package_path, tmp_path, name="EDIÇÃO DO ENGINE")

    project.products[0].display_name = "ALTERAÇÃO NOVA NO STUDIO"
    result = sync_saved_session_to_project(project, tmp_path)

    assert not result.ok
    assert result.report is not None and result.report.conflict
    assert project.products[0].display_name == "ALTERAÇÃO NOVA NO STUDIO"
