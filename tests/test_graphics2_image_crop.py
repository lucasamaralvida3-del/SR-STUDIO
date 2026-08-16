from __future__ import annotations

from pathlib import Path

import pytest

import srstudio
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.image_crop import MAX_CROP_TOTAL, crop_pixel_box, normalize_crop, update_crop
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.preflight import run_preflight


def _image_session(kind: NodeKind = NodeKind.IMAGE) -> tuple[GraphicsSession, str]:
    session = GraphicsSession()
    node = GraphicsNode(kind=kind, transform=Transform(x=10, y=20, width=300, height=200))
    session.page.add_node(node)
    session.select(node.id)
    return session, node.id


def test_crop_normalization_accepts_ooxml_and_long_keys() -> None:
    short = normalize_crop({"l": 0.10, "t": 0.20, "r": 0.15, "b": 0.05})
    long = normalize_crop({"left": 0.10, "top": 0.20, "right": 0.15, "bottom": 0.05})
    assert short == long
    assert short.width_fraction == pytest.approx(0.75)
    assert short.height_fraction == pytest.approx(0.75)


def test_crop_never_allows_an_empty_source_rectangle() -> None:
    crop = normalize_crop({"l": 0.98, "r": 0.98, "t": 0.98, "b": 0.98})
    assert crop.left + crop.right == pytest.approx(MAX_CROP_TOTAL)
    assert crop.top + crop.bottom == pytest.approx(MAX_CROP_TOTAL)
    x, y, width, height = crop_pixel_box(1000, 500, crop)
    assert 0 <= x < 1000
    assert 0 <= y < 500
    assert width >= 1
    assert height >= 1
    assert x + width <= 1000
    assert y + height <= 500


def test_partial_crop_update_preserves_opposite_edge_and_clamps_changed_edge() -> None:
    current = {"l": 0.20, "t": 0.0, "r": 0.70, "b": 0.0}
    crop = update_crop(current, left=0.60)
    assert crop.right == pytest.approx(0.70)
    assert crop.left == pytest.approx(MAX_CROP_TOTAL - 0.70)


def test_session_persists_physical_crop_and_undo_redo() -> None:
    session, node_id = _image_session()
    session.set_image_crop(
        node_id,
        fit="cover",
        focus_x=0.25,
        focus_y=0.75,
        zoom=1.4,
        crop_left=0.10,
        crop_top=0.05,
        crop_right=0.20,
        crop_bottom=0.15,
    )
    style = session.page.nodes[node_id].style
    assert style["fit"] == "cover"
    assert style["focus_x"] == pytest.approx(0.25)
    assert style["zoom"] == pytest.approx(1.4)
    assert style["crop"] == pytest.approx({"l": 0.10, "t": 0.05, "r": 0.20, "b": 0.15})

    assert session.undo()
    assert "crop" not in session.page.nodes[node_id].style
    assert session.redo()
    assert session.page.nodes[node_id].style["crop"]["r"] == pytest.approx(0.20)


def test_background_nodes_use_the_same_crop_contract() -> None:
    session, node_id = _image_session(NodeKind.BACKGROUND)
    session.set_image_crop(node_id, crop_left=0.12, crop_bottom=0.08)
    assert session.page.nodes[node_id].style["crop"] == pytest.approx(
        {"l": 0.12, "t": 0.0, "r": 0.0, "b": 0.08}
    )
    session.set_image_crop(node_id, crop_reset=True)
    assert "crop" not in session.page.nodes[node_id].style


def test_router_exposes_crop_edges_and_rejects_non_images() -> None:
    session, node_id = _image_session()
    router = GraphicsCommandRouter(session)
    result = router.dispatch(
        {
            "name": "crop",
            "node_id": node_id,
            "crop_left": 0.11,
            "crop_right": 0.22,
            "zoom": 1.25,
        }
    )
    assert result.ok and result.changed
    assert session.page.nodes[node_id].style["crop"]["l"] == pytest.approx(0.11)
    assert session.page.nodes[node_id].style["crop"]["r"] == pytest.approx(0.22)

    text = GraphicsNode(kind=NodeKind.TEXT, text="X", transform=Transform(width=30, height=20))
    session.page.add_node(text)
    rejected = router.dispatch({"name": "crop", "node_id": text.id, "crop_left": 0.1})
    assert not rejected.ok


def test_preflight_accepts_normalized_crop_and_framing() -> None:
    document = GraphicsDocument()
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        transform=Transform(width=200, height=100),
        style={
            "fit": "cover",
            "focus_x": 0.3,
            "focus_y": 0.8,
            "zoom": 1.5,
            "crop": {"l": 0.1, "t": 0.05, "r": 0.2, "b": 0.1},
        },
    )
    document.active_page.add_node(image)
    codes = {issue.code for issue in run_preflight(document)}
    assert "INVALID_IMAGE_CROP" not in codes
    assert "INVALID_IMAGE_FIT" not in codes
    assert "INVALID_IMAGE_FOCUS" not in codes
    assert "INVALID_IMAGE_ZOOM" not in codes


def test_preflight_blocks_invalid_crop_focus_zoom_and_fit() -> None:
    document = GraphicsDocument()
    image = GraphicsNode(
        kind=NodeKind.BACKGROUND,
        transform=Transform(width=200, height=100),
        style={
            "fit": "mystery",
            "focus_x": 1.2,
            "focus_y": "invalid",
            "zoom": 0,
            "crop": {"l": 0.8, "t": 0.0, "r": 0.7, "b": 0.0},
        },
    )
    document.active_page.add_node(image)
    issues = run_preflight(document)
    codes = {issue.code for issue in issues if issue.severity == "error"}
    assert {"INVALID_IMAGE_CROP", "INVALID_IMAGE_FIT", "INVALID_IMAGE_FOCUS", "INVALID_IMAGE_ZOOM"} <= codes


def test_qml_crop_preview_has_source_clip_and_all_four_controls() -> None:
    qml_dir = Path(srstudio.__file__).with_name("graphics2") / "qml"
    scene_image = (qml_dir / "SceneImage.qml").read_text(encoding="utf-8")
    inspector = (qml_dir / "ImageInspector.qml").read_text(encoding="utf-8")
    assert "sourceClipRect: Qt.rect(" in scene_image
    for prop in ("cropLeft", "cropTop", "cropRight", "cropBottom"):
        assert f"property real {prop}" in scene_image
    assert 'command["crop_" + edge] = value' in inspector
    for edge in ("left", "top", "right", "bottom"):
        assert f'applyCrop("{edge}", value)' in inspector
    assert '"crop_reset": true' in inspector
