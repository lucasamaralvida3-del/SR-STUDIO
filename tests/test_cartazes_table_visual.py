from decimal import Decimal
from types import SimpleNamespace

from srstudio.app.cartazes_table_visual import (
    POSTER_COPIES_MAX,
    ROW_EDITED,
    ROW_ERROR,
    ROW_EVEN,
    ROW_ODD,
    ROW_WARNING,
    SELECTION_BACKGROUND,
    SELECTION_FOREGROUND,
    cartazes_row_tag,
    cartazes_status_label,
    expand_promotion_products,
    poster_copy_count,
    promotion_price_text,
    should_clear_initial_promotion_selection,
)
from srstudio.posters.commercial import PosterCommercialValidator


def test_error_row_has_highest_visual_priority() -> None:
    assert cartazes_row_tag(PosterCommercialValidator.ERROR, "", False, 0) == ROW_ERROR
    assert cartazes_row_tag("", "ERRO", True, 1) == ROW_ERROR
    assert cartazes_status_label(PosterCommercialValidator.ERROR) == "⛔ ERRO"
    assert cartazes_status_label("", "ERRO") == "⛔ ERRO"


def test_attention_row_is_distinct_from_normal_rows() -> None:
    assert cartazes_row_tag(PosterCommercialValidator.WARNING, "", False, 0) == ROW_WARNING
    assert cartazes_status_label(PosterCommercialValidator.WARNING) == "⚠ ATENÇÃO"


def test_normal_rows_are_zebra_striped() -> None:
    assert cartazes_row_tag("", "", False, 0) == ROW_EVEN
    assert cartazes_row_tag("", "", False, 1) == ROW_ODD
    assert cartazes_row_tag("", "", False, 2) == ROW_EVEN


def test_edited_row_remains_visible_without_looking_like_error() -> None:
    assert cartazes_row_tag("", "ALTERADO", True, 0) == ROW_EDITED
    assert cartazes_status_label("", "ALTERADO", True) == "● ALTERADO"


def test_rendering_state_keeps_clear_status() -> None:
    assert cartazes_status_label("", "AGUARDANDO") == "◌ RENDER"
    assert cartazes_status_label("", "RENDERIZANDO") == "◌ RENDER"
    assert cartazes_status_label("", "PRONTO") == "✓ OK"


def test_initial_promotion_selection_is_preserved_for_print_control() -> None:
    assert not should_clear_initial_promotion_selection(
        is_wholesale=False,
        item_count=37,
        selected_count=37,
    )
    assert not should_clear_initial_promotion_selection(
        is_wholesale=False,
        item_count=37,
        selected_count=1,
    )
    assert not should_clear_initial_promotion_selection(
        is_wholesale=True,
        item_count=37,
        selected_count=37,
    )


def test_promotion_price_text_never_appends_unit() -> None:
    assert promotion_price_text(Decimal("33.64")) == "R$ 33,64"
    assert promotion_price_text(Decimal("9.87")) == "R$ 9,87"
    assert "UN" not in promotion_price_text(Decimal("17.78"))
    assert promotion_price_text(None) == "—"


def test_poster_copy_count_defaults_to_one_and_clamps_invalid_values() -> None:
    assert poster_copy_count(SimpleNamespace(metadata={})) == 1
    assert poster_copy_count(SimpleNamespace(metadata={"poster_copies": "3"})) == 3
    assert poster_copy_count(SimpleNamespace(metadata={"poster_copies": 0})) == 1
    assert poster_copy_count(SimpleNamespace(metadata={"poster_copies": 999})) == POSTER_COPIES_MAX
    assert poster_copy_count(SimpleNamespace(metadata={"poster_copies": "abc"})) == 1


def test_expand_promotion_products_repeats_each_selected_product() -> None:
    first = SimpleNamespace(metadata={"poster_copies": 2})
    second = SimpleNamespace(metadata={"poster_copies": 3})
    expanded = expand_promotion_products([first, second])
    assert expanded == [first, first, second, second, second]


def test_selection_palette_keeps_text_readable() -> None:
    assert SELECTION_BACKGROUND != SELECTION_FOREGROUND
    assert SELECTION_FOREGROUND == "#102A43"
