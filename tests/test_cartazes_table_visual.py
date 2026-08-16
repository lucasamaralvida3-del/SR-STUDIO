from srstudio.app.cartazes_table_visual import (
    ROW_EDITED,
    ROW_ERROR,
    ROW_EVEN,
    ROW_ODD,
    ROW_WARNING,
    cartazes_row_tag,
    cartazes_status_label,
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
