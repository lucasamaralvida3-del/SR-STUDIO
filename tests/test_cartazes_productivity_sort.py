from decimal import Decimal

from srstudio.app.cartazes_productivity import _decimal_key, _natural_text


def test_natural_text_orders_numeric_codes_naturally() -> None:
    values = ["100", "9", "20", "2"]
    assert sorted(values, key=_natural_text) == ["2", "9", "20", "100"]


def test_decimal_key_places_missing_values_last_ascending() -> None:
    values = [Decimal("31.89"), None, Decimal("7.86")]
    assert sorted(values, key=_decimal_key) == [Decimal("7.86"), Decimal("31.89"), None]
