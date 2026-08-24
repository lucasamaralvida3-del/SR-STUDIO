from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from srstudio.graphics2 import qt_renderer
from srstudio.graphics2.qt_renderer import (
    _pptx_effective_horizontal_overflow,
    _pptx_effective_latin_line_break,
    _pptx_office_line_break_segments,
    _pptx_shape_autofit_single_line_layout,
    _pptx_shape_autofit_wrapped_layout,
)


@pytest.fixture(scope="module")
def qt():
    pyside = pytest.importorskip("PySide6")
    QtCore = pyside.QtCore
    QtGui = pyside.QtGui
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    return QtCore, QtGui, app


def _font(QtGui, px: int = 18):
    font = QtGui.QFont("Arial")
    font.setPixelSize(px)
    return font


def _style(**overrides):
    style = {
        "align": "center",
        "v_align": "top",
        "nowrap": False,
        "pptx_wrap": "square",
        "pptx_auto_fit": "shape",
        "fit_inside_box": False,
        "semantic_fit_policy": "preserve_source_typography",
        "font_size": 13.5,
        "font_size_unit": "pt",
    }
    style.update(overrides)
    return style


def _narrow_rect(text: str, font, QtCore, QtGui):
    metrics = QtGui.QFontMetricsF(font)
    widest = max(float(metrics.horizontalAdvance(ch)) for ch in text)
    full = float(metrics.horizontalAdvance(text))
    assert full > widest
    return QtCore.QRectF(10.0, 20.0, max(widest + 0.25, full * 0.58), 8.0)


def test_office_effective_defaults_apply_only_to_known_pptx_text():
    assert _pptx_effective_latin_line_break(_style()) is False
    assert _pptx_effective_horizontal_overflow(_style()) == "overflow"
    assert _pptx_effective_latin_line_break({"nowrap": False}) is None
    assert _pptx_effective_horizontal_overflow({"nowrap": False}) == ""


def test_explicit_office_values_override_defaults():
    style = _style(pptx_latin_ln_brk=True, pptx_horz_overflow="clip")
    assert _pptx_effective_latin_line_break(style) is True
    assert _pptx_effective_horizontal_overflow(style) == "clip"


def test_latin_word_is_indivisible_when_latin_ln_brk_false(qt):
    QtCore, _, _ = qt
    segments = _pptx_office_line_break_segments(
        "KG",
        1.0,
        _style(pptx_latin_ln_brk=False),
        lambda value: float(len(value)),
        QtCore,
    )
    assert segments == ["KG"]


def test_latin_word_can_break_when_latin_ln_brk_true(qt):
    QtCore, _, _ = qt
    segments = _pptx_office_line_break_segments(
        "KG",
        1.0,
        _style(pptx_latin_ln_brk=True),
        lambda value: float(len(value)),
        QtCore,
    )
    assert segments == ["K", "G"]


def test_latin_words_protected_in_mixed_sentence(qt):
    QtCore, _, _ = qt
    segments = _pptx_office_line_break_segments(
        "AB CD",
        3.0,
        _style(pptx_latin_ln_brk=False),
        lambda value: float(len(value)),
        QtCore,
    )
    assert segments == ["AB ", "CD"]
    assert "".join(segments) == "AB CD"


def test_non_latin_word_currency_can_emergency_break(qt):
    QtCore, _, _ = qt
    segments = _pptx_office_line_break_segments(
        "R$",
        1.0,
        _style(pptx_latin_ln_brk=False),
        lambda value: float(len(value)),
        QtCore,
    )
    assert segments == ["R", "$"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (",86", [",8", "6"]),
        (",74", [",7", "4"]),
        (",73", [",7", "3"]),
        (",72", [",7", "2"]),
    ],
)
def test_decimal_oracles_follow_longest_fitting_prefix(text, expected, qt):
    QtCore, _, _ = qt
    segments = _pptx_office_line_break_segments(
        text,
        2.0,
        _style(pptx_latin_ln_brk=False),
        lambda value: float(len(value)),
        QtCore,
    )
    assert segments == expected


def test_square_shape_autofit_wraps_narrow_currency_without_manual_break(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    rect = _narrow_rect("R$", font, QtCore, QtGui)
    layout = _pptx_shape_autofit_wrapped_layout("R$", rect, _style(), font, QtCore, QtGui)
    assert layout is not None
    assert len(layout) == 2
    assert "".join(line for line, _, _ in layout) == "R$"


def test_square_shape_autofit_emergency_wraps_decimal_by_longest_prefix(qt):
    QtCore, QtGui, _ = qt
    text = ",86"
    font = _font(QtGui)
    rect = _narrow_rect(text, font, QtCore, QtGui)
    layout = _pptx_shape_autofit_wrapped_layout(text, rect, _style(), font, QtCore, QtGui)
    assert layout is not None
    assert len(layout) == 2
    assert "".join(line for line, _, _ in layout) == text


def test_narrow_latin_word_stays_one_line_and_uses_explicit_overflow_baseline(qt):
    QtCore, QtGui, _ = qt
    text = "KG"
    font = _font(QtGui)
    rect = _narrow_rect(text, font, QtCore, QtGui)
    style = _style(pptx_latin_ln_brk=False, pptx_horz_overflow="overflow")
    assert _pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui) is None
    assert _pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui) is not None


def test_narrow_latin_word_breaks_when_latin_ln_brk_true(qt):
    QtCore, QtGui, _ = qt
    text = "KG"
    font = _font(QtGui)
    rect = _narrow_rect(text, font, QtCore, QtGui)
    style = _style(pptx_latin_ln_brk=True)
    layout = _pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui)
    assert layout is not None
    assert [line for line, _, _ in layout] == ["K", "G"]


def test_square_shape_autofit_that_fits_stays_on_explicit_baseline(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    metrics = QtGui.QFontMetricsF(font)
    rect = QtCore.QRectF(0.0, 0.0, float(metrics.horizontalAdvance("24")) + 8.0, 8.0)
    style = _style(font_size=18.0, font_size_unit="px")
    assert _pptx_shape_autofit_wrapped_layout("24", rect, style, font, QtCore, QtGui) is None
    assert _pptx_shape_autofit_single_line_layout("24", rect, style, font, QtGui) is not None


def test_nowrap_overflow_stays_single_line(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    rect = _narrow_rect("R$", font, QtCore, QtGui)
    style = _style(nowrap=True)
    assert _pptx_shape_autofit_wrapped_layout("R$", rect, style, font, QtCore, QtGui) is None
    assert _pptx_shape_autofit_single_line_layout("R$", rect, style, font, QtGui) is not None


@pytest.mark.parametrize("text", ["24", "KG"])
def test_fitting_integer_and_unit_like_text_preserve_explicit_baseline(text, qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    metrics = QtGui.QFontMetricsF(font)
    rect = QtCore.QRectF(0.0, 0.0, float(metrics.horizontalAdvance(text)) + 6.0, 7.0)
    style = _style(font_size=18.0, font_size_unit="px")
    assert _pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui) is None
    assert _pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui) is not None


def test_wrapped_layout_uses_explicit_drawingml_line_spacing(qt):
    QtCore, QtGui, _ = qt
    font = _font(QtGui)
    rect = _narrow_rect("R$", font, QtCore, QtGui)
    layout = _pptx_shape_autofit_wrapped_layout(
        "R$", rect, _style(line_spacing_px=13.28), font, QtCore, QtGui
    )
    assert layout is not None and len(layout) == 2
    assert layout[1][2] - layout[0][2] == pytest.approx(13.28)


def test_marginal_ink_overflow_is_not_accepted_by_advance_alone(qt, monkeypatch):
    QtCore, QtGui, _ = qt
    text = ",86"
    font = _font(QtGui)
    metrics = QtGui.QFontMetricsF(font)
    rect_width = float(metrics.horizontalAdvance(text)) + 1.0
    rect = QtCore.QRectF(0.0, 0.0, rect_width, 8.0)
    style = _style(font_size=18.0, font_size_unit="px")

    def ink_aware_width(value, *_args):
        widths = {
            ",86": rect_width + 1.0,
            ",8": rect_width - 0.1,
            ",": max(1.0, rect_width * 0.35),
            "8": max(1.0, rect_width * 0.35),
            "6": max(1.0, rect_width * 0.35),
        }
        return widths[value]

    monkeypatch.setattr(qt_renderer, "_pptx_source_layout_width", ink_aware_width)
    assert float(metrics.horizontalAdvance(text)) < rect.width()
    assert ink_aware_width(text) > rect.width() + 0.01
    layout = qt_renderer._pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui)
    assert layout is not None
    assert [line for line, _, _ in layout] == [",8", "6"]
    assert qt_renderer._pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui) is None


def test_emergency_wrap_preserves_unicode_grapheme_clusters(qt):
    QtCore, _, _ = qt
    assert qt_renderer._pptx_grapheme_clusters("A\u0301B", QtCore) == ["A\u0301", "B"]
