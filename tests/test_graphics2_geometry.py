from __future__ import annotations

from srstudio.graphics2.geometry import SnapEngine, SnapSettings, ViewportTransform, hit_test
from srstudio.graphics2.model import GraphicsNode, GraphicsPage, NodeKind, Transform


def test_viewport_zoom_does_not_change_document_geometry():
    viewport = ViewportTransform(zoom=2.0, pan_x=100, pan_y=50); screen = viewport.document_to_screen(20, 30)
    assert screen == (140, 110); assert viewport.screen_to_document(*screen) == (20, 30); viewport.zoom_at(1.5, *screen); assert viewport.screen_to_document(*screen) == (20, 30)


def test_snap_uses_screen_tolerance_but_returns_document_delta():
    page = GraphicsPage(width=1000, height=1000); moving = GraphicsNode(kind=NodeKind.RECT, transform=Transform(x=95, y=100, width=100, height=100)); target = GraphicsNode(kind=NodeKind.RECT, transform=Transform(x=300, y=100, width=100, height=100)); page.add_node(moving); page.add_node(target)
    result = SnapEngine.snap_move(page, [moving.id], 101, 0, zoom=1.0, settings=SnapSettings(tolerance_screen_px=7)); assert result.dx == 105; assert result.guide_x == 300


def test_hit_test_handles_rotation_and_z_order():
    page = GraphicsPage(); low = GraphicsNode(kind=NodeKind.RECT, transform=Transform(x=0, y=0, width=100, height=100), z_index=1); high = GraphicsNode(kind=NodeKind.RECT, transform=Transform(x=20, y=20, width=100, height=100, rotation=15), z_index=2); page.add_node(low); page.add_node(high)
    assert hit_test(page, 50, 50).id == high.id
