from srstudio.editor.layout import Rect
from srstudio.editor.viewport import ViewportTransform, contains, resize_handle


def test_viewport_roundtrip():
    transform = ViewportTransform(1080, 1350, 800, 700, zoom=0.9)
    sx, sy = transform.to_screen(420, 330)
    px, py = transform.to_page(sx, sy)
    assert abs(px - 420) < 0.001
    assert abs(py - 330) < 0.001


def test_page_bounds_fit_viewport():
    transform = ViewportTransform(1080, 1350, 900, 800, padding=20, zoom=1.0)
    bounds = transform.page_bounds()
    assert bounds.width <= 860
    assert bounds.height <= 760


def test_contains_and_resize_handle():
    rect = Rect(10, 20, 100, 80)
    assert contains(rect, 50, 50)
    assert not contains(rect, 0, 0)
    handle = resize_handle(rect, 10)
    assert contains(handle, rect.right, rect.bottom)
