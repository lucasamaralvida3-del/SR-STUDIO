from srstudio.graphics2.qt_renderer import _should_fit_text, _text_flags


class _Qt:
    AlignLeft = 0x0001
    AlignRight = 0x0002
    AlignHCenter = 0x0004
    AlignTop = 0x0020
    AlignBottom = 0x0040
    AlignVCenter = 0x0080
    TextSingleLine = 0x0100
    TextWordWrap = 0x1000


class _QtCore:
    Qt = _Qt


def test_nowrap_only_controls_wrapping_not_font_size():
    assert _should_fit_text({"nowrap": True, "fit_inside_box": False}) is False


def test_explicit_fit_inside_box_keeps_auto_fit_behavior():
    assert _should_fit_text({"fit_inside_box": True}) is True


def test_priceblock_overflow_policy_can_shrink_only_when_needed():
    assert _should_fit_text({"nowrap": True, "semantic_fit_policy": "overflow_only"}) is True


def test_nowrap_disables_automatic_wrap_without_forcing_single_line():
    flags = _text_flags({"nowrap": True, "align": "left", "v_align": "top"}, _QtCore)

    assert flags & _Qt.AlignLeft
    assert flags & _Qt.AlignTop
    assert not flags & _Qt.TextWordWrap
    assert not flags & _Qt.TextSingleLine


def test_wrapped_text_keeps_qpainter_word_wrap():
    flags = _text_flags({"nowrap": False, "align": "center", "v_align": "center"}, _QtCore)

    assert flags & _Qt.AlignHCenter
    assert flags & _Qt.AlignVCenter
    assert flags & _Qt.TextWordWrap
    assert not flags & _Qt.TextSingleLine
