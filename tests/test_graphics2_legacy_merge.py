from __future__ import annotations

from decimal import Decimal

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.legacy_merge import (
    analyze_legacy_merge,
    merge_graphics_to_studio_non_conflicting,
    resolve_legacy_merge_conflicts,
)
from srstudio.graphics2.model import BindingRole
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.studio_bridge import prepare_studio_project, sync_saved_session_to_project


def _project() -> StudioProject:
    product = Product(display_name="ACÉM KG", price="25,77", unit="KG")
    card = ProductCard(product_id=product.id, x=100, y=140, width=320, height=250)
    return StudioProject(name="Quinta Filé", products=[product], pages=[Page(name="Página 1", cards=[card])])


def _edit_g2_price(document, whole: str, cents: str) -> None:
    page = document.active_page
    slot = next(iter(page.slots.values()))
    page.nodes[slot.node_by_role[BindingRole.PRICE_REAIS.value]].text = whole
    page.nodes[slot.node_by_role[BindingRole.PRICE_CENTS.value]].text = cents


def _g2_name(document) -> str:
    page = document.active_page
    slot = next(iter(page.slots.values()))
    return page.nodes[slot.node_by_role[BindingRole.NAME.value]].text


def test_prepare_records_base_fingerprint_and_reuses_unchanged_session(tmp_path):
    project = _project()
    first = prepare_studio_project(project, tmp_path, graphics_api="software")
    assert not first.reused_session

    document = load_package(first.package_path, extract_assets_to=tmp_path / "extract-1")
    assert document.metadata["legacy_source_fingerprint"]
    assert document.metadata["legacy_source_snapshot"]["id"] == project.id

    marker = document.active_page.name = "Página alterada somente no G2"
    save_package(document, first.package_path)

    second = prepare_studio_project(project, tmp_path, graphics_api="software")
    assert second.reused_session
    reopened = load_package(second.package_path, extract_assets_to=tmp_path / "extract-2")
    assert reopened.active_page.name == marker


def test_three_way_merge_applies_g2_price_and_preserves_independent_studio_name(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    _edit_g2_price(document, "29", ",90")
    save_package(document, prepared.package_path)

    project.products[0].display_name = "ACÉM BOVINO KG"
    blocked = sync_saved_session_to_project(project, tmp_path)
    assert not blocked.ok
    assert blocked.report is not None and blocked.report.conflict

    merged = sync_saved_session_to_project(project, tmp_path, merge_non_conflicting=True)
    assert merged.ok
    assert merged.report is not None
    assert not merged.report.conflict
    assert project.products[0].display_name == "ACÉM BOVINO KG"
    assert project.products[0].price == Decimal("29.90")

    # A mudança feita somente no Studio também precisa ser reconciliada no G2
    # antes de avançar a BASE; caso contrário a próxima sessão tentaria voltar
    # o nome antigo ao Studio.
    reopened = load_package(prepared.package_path, extract_assets_to=tmp_path / "reopen")
    assert _g2_name(reopened) == "ACÉM BOVINO KG"
    assert not analyze_legacy_merge(reopened, project).conflict


def test_three_way_merge_keeps_studio_value_when_same_field_changed_on_both_sides(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    _edit_g2_price(document, "29", ",90")
    save_package(document, prepared.package_path)

    project.products[0].price = Decimal("27.50")
    analysis = analyze_legacy_merge(document, project)
    assert analysis.ok
    assert analysis.conflict
    assert any(item.path.endswith("/price") for item in analysis.conflicts)

    report = merge_graphics_to_studio_non_conflicting(document, project)
    assert report.ok
    assert report.conflict
    assert project.products[0].price == Decimal("27.50")


def test_merge_applies_non_conflicting_card_geometry_while_preserving_studio_product_change(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    group = document.active_page.nodes[project.pages[0].cards[0].id]
    group.transform.x = 222
    group.transform.y = 333
    save_package(document, prepared.package_path)

    project.products[0].display_name = "ACÉM PREMIUM KG"
    result = sync_saved_session_to_project(project, tmp_path, merge_non_conflicting=True)
    assert result.ok
    assert project.products[0].display_name == "ACÉM PREMIUM KG"
    assert project.pages[0].cards[0].x == 222
    assert project.pages[0].cards[0].y == 333


def test_explicit_conflict_resolution_can_choose_studio_and_updates_g2_representation(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    page = document.active_page
    slot = next(iter(page.slots.values()))
    page.nodes[slot.node_by_role[BindingRole.NAME.value]].text = "ACÉM G2 KG"

    project.products[0].display_name = "ACÉM STUDIO KG"
    analysis = analyze_legacy_merge(document, project)
    name_conflict = next(item for item in analysis.conflicts if item.path.endswith("/display_name"))

    resolved = resolve_legacy_merge_conflicts(document, project, {name_conflict.path: "studio"})

    assert resolved.ok
    assert not resolved.conflict
    assert resolved.resolved == 1
    assert project.products[0].display_name == "ACÉM STUDIO KG"
    assert _g2_name(document) == "ACÉM STUDIO KG"
    assert document.metadata["legacy_source_fingerprint"] == resolved.result_fingerprint


def test_explicit_conflict_resolution_can_choose_graphics2_price(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    _edit_g2_price(document, "31", ",45")
    project.products[0].price = Decimal("27.50")

    analysis = analyze_legacy_merge(document, project)
    price_conflict = next(item for item in analysis.conflicts if item.path.endswith("/price"))
    resolved = resolve_legacy_merge_conflicts(document, project, {price_conflict.path: "graphics2"})

    assert resolved.ok
    assert not resolved.conflict
    assert resolved.decisions[price_conflict.path] == "graphics2"
    assert project.products[0].price == Decimal("31.45")


def test_unresolved_field_remains_conflict_when_no_decision_is_supplied(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path)
    document = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    _edit_g2_price(document, "29", ",90")
    project.products[0].price = Decimal("27.50")

    report = resolve_legacy_merge_conflicts(document, project, {})

    assert report.ok
    assert report.conflict
    assert report.unresolved_conflicts == 1
    assert project.products[0].price == Decimal("27.50")
