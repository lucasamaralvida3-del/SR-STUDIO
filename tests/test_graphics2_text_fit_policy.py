from srstudio.graphics2.qt_renderer import _should_fit_text


def test_nowrap_only_controls_wrapping_not_font_size():
    assert _should_fit_text({"nowrap": True, "fit_inside_box": False}) is False


def test_explicit_fit_inside_box_keeps_auto_fit_behavior():
    assert _should_fit_text({"fit_inside_box": True}) is True


def test_priceblock_overflow_policy_can_shrink_only_when_needed():
    assert _should_fit_text({"nowrap": True, "semantic_fit_policy": "overflow_only"}) is True
