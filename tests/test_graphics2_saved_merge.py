from __future__ import annotations

from decimal import Decimal

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.model import BindingRole
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.saved_merge import analyze_saved_session_merge, resolve_saved_session_merge
from srstudio.graphics2.studio_bridge import prepare_studio_project


def _project() -> StudioProject:
    product = Product(display_name="ACÉM KG", price="25,77", unit="KG")
    card = ProductCard(product_id=product.id, x=100, y=140, width=320, height=250)
    return StudioProject(name="Quinta Filé", products=[product], pages=[Page(name="Página 1", cards=[card])])


def _edit_g2_name(document, value: str) -> None:
    page = document.active_page
    slot = next(iter(page.slots.values()))
    page.nodes[slot.node_by_role[BindingRole.NAME.value]].text = value


def _edit_g2_price(document, whole: str, cents: str) -> None:
    page = document.active_page
    slot = next(iter(page.slots.values()))
    page.nodes[slot.node_by_role[BindingRole.PRICE_REAIS.value]].text = whole
    page.nodes[slot.node_by_role[BindingRole.PRICE_CENTS.value]].text = cents


def test_saved_merge_analysis_reports_real_conflict_without_mutating_project(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    _edit_g2_price(document, "31", ",45")
    save_package(document, prepared.package_path)
    project.products[0].price = Decimal("27.50")

    result = analyze_saved_session_merge(project, tmp_path)

    assert result.ok
    assert result.report is not None and result.report.conflict
    assert project.products[0].price == Decimal("27.50")
    assert any(item.path.endswith("/price") for item in result.report.conflicts)


def test_saved_merge_resolves_field_and_persists_converged_session(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    _edit_g2_name(document, "ACÉM G2 KG")
    save_package(document, prepared.package_path)
    project.products[0].display_name = "ACÉM STUDIO KG"

    analysis = analyze_saved_session_merge(project, tmp_path)
    conflict = next(item for item in analysis.report.conflicts if item.path.endswith("/display_name"))
    resolved = resolve_saved_session_merge(project, tmp_path, {conflict.path: "studio"})

    assert resolved.ok
    assert resolved.report is not None and not resolved.report.conflict
    assert project.products[0].display_name == "ACÉM STUDIO KG"
    reopened = load_package(prepared.package_path, extract_assets_to=tmp_path / "reopened")
    page = reopened.active_page
    slot = next(iter(page.slots.values()))
    assert page.nodes[slot.node_by_role[BindingRole.NAME.value]].text == "ACÉM STUDIO KG"


def test_saved_merge_does_not_mutate_live_project_when_package_save_fails(tmp_path, monkeypatch):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    _edit_g2_price(document, "31", ",45")
    save_package(document, prepared.package_path)
    project.products[0].price = Decimal("27.50")

    analysis = analyze_saved_session_merge(project, tmp_path)
    conflict = next(item for item in analysis.report.conflicts if item.path.endswith("/price"))

    def fail_save(*args, **kwargs):
        raise OSError("disco indisponível")

    monkeypatch.setattr("srstudio.graphics2.saved_merge.save_package", fail_save)
    result = resolve_saved_session_merge(project, tmp_path, {conflict.path: "graphics2"})

    assert not result.ok
    assert project.products[0].price == Decimal("27.50")
