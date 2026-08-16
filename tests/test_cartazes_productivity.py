from decimal import Decimal

from srstudio.app.cartazes_productivity import (
    cartazes_diagnostic_label,
    cartazes_matches_filter,
    cartazes_problem_priority,
    safe_unit_correction,
)
from srstudio.core.models import Product
from srstudio.posters.commercial import CommercialIssue, CommercialStatus, PosterCommercialValidator


def test_status_column_shows_compact_actionable_issue_name() -> None:
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
    assert cartazes_diagnostic_label(status) == "⛔ < CUSTO"


def test_attention_status_prioritizes_specific_diagnosis() -> None:
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
    assert cartazes_diagnostic_label(status) == "⚠ CLUBE >"


def test_render_error_has_priority_over_commercial_attention() -> None:
    status = CommercialStatus(overall=PosterCommercialValidator.WARNING)
    assert cartazes_diagnostic_label(status, "ERRO") == "⛔ RENDER"
    assert cartazes_problem_priority(status, "ERRO") == 0


def test_problem_priority_orders_error_attention_edited_and_ok() -> None:
    error = CommercialStatus(overall=PosterCommercialValidator.ERROR)
    attention = CommercialStatus(overall=PosterCommercialValidator.WARNING)
    ok = CommercialStatus(overall=PosterCommercialValidator.OK)

    assert cartazes_problem_priority(error) == 0
    assert cartazes_problem_priority(attention) == 1
    assert cartazes_problem_priority(ok, edited=True) == 2
    assert cartazes_problem_priority(ok, "RENDERIZANDO") == 3
    assert cartazes_problem_priority(ok) == 4


def test_problem_filter_includes_errors_attention_and_render_failures() -> None:
    error = CommercialStatus(overall=PosterCommercialValidator.ERROR)
    attention = CommercialStatus(overall=PosterCommercialValidator.WARNING)
    ok = CommercialStatus(overall=PosterCommercialValidator.OK)

    assert cartazes_matches_filter("PROBLEMAS", error, "")
    assert cartazes_matches_filter("PROBLEMAS", attention, "")
    assert cartazes_matches_filter("PROBLEMAS", ok, "ERRO")
    assert not cartazes_matches_filter("PROBLEMAS", ok, "PRONTO")
    assert cartazes_matches_filter("ERROS", ok, "ERRO")
    assert cartazes_matches_filter("ALERTAS", attention, "")


def test_existing_filters_remain_compatible() -> None:
    ok = CommercialStatus(overall=PosterCommercialValidator.OK)
    assert cartazes_matches_filter("TODOS", ok, "")
    assert cartazes_matches_filter("ALTERADOS", ok, "", edited=True)
    assert cartazes_matches_filter("COM LIMITE", ok, "", has_limit=True)
    assert cartazes_matches_filter("COM CLUBE", ok, "", has_secondary=True)


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
