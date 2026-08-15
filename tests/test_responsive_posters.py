from srstudio.app.responsive_posters import poster_pane_ratio, preview_bounds


def test_poster_pane_ratio_prefers_visible_preview_on_wide_windows() -> None:
    assert poster_pane_ratio(1600) == (68, 32)
    assert poster_pane_ratio(1400) == (66, 34)
    assert poster_pane_ratio(1200) == (64, 36)
    assert poster_pane_ratio(1000) == (62, 38)


def test_preview_bounds_keep_margins_and_cap_overscaling() -> None:
    assert preview_bounds(450, 650) == (420, 620)
    assert preview_bounds(900, 1200) == (620, 760)
    assert preview_bounds(200, 200) == (220, 280)
