from decimal import Decimal

from srstudio.app.cartazes_productivity import (
    cartazes_diagnostic_label,
    safe_unit_correction,
)
from srstudio.core.models import Product
from srstudio.posters.commercial import CommercialIssue, CommercialStatus, PosterCommercialValidator


def test_status_column_shows_actionable_issue_name() -> None:
    status = CommercialStatus(
        overall=PosterCommercialValidator.ERROR,
        issues=[
            CommercialIssue(
                "ABAIXO_CUSTO",
                PosterCommercialValidator.ERROR,
                "cost",
                "Promoção abaixo do custo.",
                "price",
            )
        ],
    )
    assert cartazes_diagnostic_label(status) == "⛔ ABAIXO CUSTO"


def test_warning_status_prioritizes_specific_diagnosis() -> None:
    status = CommercialStatus(
        overall=PosterCommercialValidator.WARNING,
        issues=[
            CommercialIssue(
                "CLUBE_MAIOR_PROMO",
                PosterCommercialValidator.WARNING,
                "club",
                "Clube maior.",
                "app_price",
            )
        ],
    )
    assert cartazes_diagnostic_label(status) == "⚠ CLUBE MAIOR"


def test_render_error_has_priority_over_commercial_warning() -> None:
    status = CommercialStatus(overall=PosterCommercialValidator.WARNING)
    assert cartazes_diagnostic_label(status, "ERRO") == "⛔ RENDER"


def test_safe_unit_correction_only_changes_deterministic_cases() -> None:
    granel = Product(original_name="ALHO A GRANEL", unit="UN")
    liquid = Product(original_name="LEITE TRIANGULO 1L", unit="KG")
    normal = Product(original_name="ACEM", unit="KG", price=Decimal("31.89"))

    assert safe_unit_correction(granel) == "KG"
    assert safe_unit_correction(liquid) == "UN"
    assert safe_unit_correction(normal) is None


def test_safe_unit_correction_normalizes_known_alias() -> None:
    product = Product(original_name="PRODUTO TESTE", unit="UND")
    assert safe_unit_correction(product) == "UN"
