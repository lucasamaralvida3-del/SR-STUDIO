from srstudio.app.cartazes_pro import (
    TABLE_COLUMNS,
    TABLE_MIN_WIDTHS,
    cartazes_generation_gate,
    cartazes_table_headers,
    cartazes_table_widths,
)


def test_promotion_table_has_all_requested_headers() -> None:
    headers = cartazes_table_headers(False)
    assert tuple(headers) == TABLE_COLUMNS
    assert headers == {
        "code": "Código",
        "name": "Produto",
        "price1": "Promoção",
        "price2": "Clube",
        "quantity": "Modo",
        "unit": "Entrada",
        "limit": "Limite",
        "check": "Status",
    }


def test_wholesale_table_keeps_business_semantics() -> None:
    headers = cartazes_table_headers(True)
    assert headers["code"] == "Código"
    assert headers["name"] == "Produto"
    assert headers["price1"] == "Varejo"
    assert headers["price2"] == "Atacado"
    assert headers["quantity"] == "Quantidade"
    assert headers["unit"] == "Entrada"
    assert headers["limit"] == "Limite"
    assert headers["check"] == "Status"


def test_table_widths_fit_available_space_without_hiding_columns() -> None:
    for available in (sum(TABLE_MIN_WIDTHS.values()), 720, 860, 1040, 1320):
        widths = cartazes_table_widths(available)
        assert tuple(widths) == TABLE_COLUMNS
        assert sum(widths.values()) == available
        assert all(widths[key] >= TABLE_MIN_WIDTHS[key] for key in TABLE_COLUMNS)


def test_generation_with_critical_error_is_safe_by_default() -> None:
    assert cartazes_generation_gate(critical=1, warnings=0, allow_errors=False) == "block"
    assert cartazes_generation_gate(critical=3, warnings=2, allow_errors=False) == "block"


def test_generation_with_error_requires_explicit_confirmation_when_enabled() -> None:
    assert cartazes_generation_gate(critical=1, warnings=0, allow_errors=True) == "confirm_errors"
    assert cartazes_generation_gate(critical=2, warnings=4, allow_errors=True) == "confirm_errors"


def test_warning_only_batch_keeps_existing_confirmation() -> None:
    assert cartazes_generation_gate(critical=0, warnings=2, allow_errors=False) == "confirm_warnings"
    assert cartazes_generation_gate(critical=0, warnings=2, allow_errors=True) == "confirm_warnings"
    assert cartazes_generation_gate(critical=0, warnings=0, allow_errors=False) == "proceed"
