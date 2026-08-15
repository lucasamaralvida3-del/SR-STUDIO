from srstudio.app.components import TONE_COLORS
from srstudio.app.design import COLORS, LAYOUT, NAV_SECTIONS, PAGE_META
from srstudio.app.encartes_professional_view import ProfessionalEncartesStudioView, ProfessionalFlyerCanvas
from srstudio.app.professional import PRIMARY_WORKFLOWS, SRStudioProfessional
from srstudio.app.workspace import SRStudioWorkspace
from srstudio.templates.registry import TemplateRegistry


def test_professional_entrypoint_extends_stable_workspace():
    assert issubclass(SRStudioProfessional, SRStudioWorkspace)


def test_professional_editor_keeps_stable_editor_contract():
    assert ProfessionalEncartesStudioView.__name__ == "ProfessionalEncartesStudioView"
    assert ProfessionalFlyerCanvas.__name__ == "ProfessionalFlyerCanvas"
    for method in ("_build", "_build_library", "_build_properties", "_refresh_pages"):
        assert hasattr(ProfessionalEncartesStudioView, method)


def test_design_system_has_required_application_tokens():
    assert COLORS.primary.startswith("#")
    assert COLORS.sidebar.startswith("#")
    assert COLORS.promotion.startswith("#")
    assert COLORS.wholesale.startswith("#")
    assert LAYOUT["sidebar_width"] >= 220
    assert "primary" in TONE_COLORS
    assert "success" in TONE_COLORS
    assert PAGE_META["Encartes Studio"][0] == "Encartes Studio"
    labels = {label for _, items in NAV_SECTIONS for label in items}
    assert {"Início", "Encartes Studio", "Validação", "Exportação", "SR IA"}.issubset(labels)


def test_promotion_and_wholesale_are_primary_workflows():
    assert set(PRIMARY_WORKFLOWS) == {"Promoções", "Atacado"}
    assert PRIMARY_WORKFLOWS["Promoções"]["mode"] == "promotion"
    assert PRIMARY_WORKFLOWS["Promoções"]["template"] == "promocao"
    assert PRIMARY_WORKFLOWS["Atacado"]["mode"] == "wholesale"
    assert PRIMARY_WORKFLOWS["Atacado"]["template"] == "atacado"
    assert "Promoções" in PAGE_META
    assert "Atacado" in PAGE_META


def test_primary_workflow_templates_exist(tmp_path):
    registry = TemplateRegistry(tmp_path)
    promotion = registry.load("promocao")
    wholesale = registry.load("atacado")
    assert promotion.settings["mode"] == "promotion"
    assert wholesale.settings["mode"] == "wholesale"
    assert wholesale.settings["two_prices"] is True
