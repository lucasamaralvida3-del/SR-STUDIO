from __future__ import annotations

import pytest

from srstudio.graphics2.slot_corpus_full_card import MEAT_STRIP_FULL_CARD_PROFILES


def test_exact_meat_strip_wrap_contract_is_square_not_nowrap():
    for profile in MEAT_STRIP_FULL_CARD_PROFILES.values():
        for role in ("name", "currency", "integer", "decimal", "unit"):
            style = profile["roles"][role]["style"]
            assert style["pptx_wrap"] == "square"
            assert style["nowrap"] is False


def test_exact_meat_strip_multiline_roles_preserve_source_line_spacing_only_where_needed():
    for profile in MEAT_STRIP_FULL_CARD_PROFILES.values():
        currency = profile["roles"]["currency"]["style"]
        decimal = profile["roles"]["decimal"]["style"]
        assert currency["line_spacing_pt"] == pytest.approx(9.96)
        assert currency["line_spacing_px"] == pytest.approx(9.96 * 96.0 / 72.0)
        assert decimal["line_spacing_pt"] == pytest.approx(8.42)
        assert decimal["line_spacing_px"] == pytest.approx(8.42 * 96.0 / 72.0)
        for role in ("name", "integer", "unit"):
            assert "line_spacing_pt" not in profile["roles"][role]["style"]
            assert "line_spacing_px" not in profile["roles"][role]["style"]
