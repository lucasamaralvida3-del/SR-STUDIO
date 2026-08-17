from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image as PILImage

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.qt_image_provider import (
    PREVIEW_PROVIDER_NAME,
    create_live_scene_image_provider,
    inject_preview_image_urls,
)
import srstudio.graphics2.qt_host as qt_host


def _document_with_image(source: str, *, node_id: str | None = None, width: float = 220, height: float = 160):
    document = GraphicsDocument(name="Provider Preview")
    kwargs = {"id": node_id} if node_id else {}
    node = GraphicsNode(
        **kwargs,
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=10, y=20, width=width, height=height),
        style={"fit": "cover", "zoom": 1.35, "focus_x": 0.25, "focus_y": 0.75},
        metadata={"bound_image_source": source},
    )
    document.active_page.add_node(node)
    return document, node


def test_injection_changes_only_serialized_preview_payload_and_preserves_original_source():
    document, node = _document_with_image("C:/Produtos/carne.png")
    payload = document.to_dict()

    injected = inject_preview_image_urls(payload, document)
    serialized = injected["pages"][0]["nodes"][node.id]

    assert node.metadata["bound_image_source"] == "C:/Produtos/carne.png"
    assert serialized["metadata"]["graphics2_preview_original_source"] == "C:/Produtos/carne.png"
    assert serialized["metadata"]["bound_image_source"].startswith(
        f"image://{PREVIEW_PROVIDER_NAME}/{node.id}/"
    )


def test_preview_signature_changes_when_crop_contract_changes():
    document, node = _document_with_image("C:/Produtos/carne.png")
    first = inject_preview_image_urls(document.to_dict(), document)
    first_url = first["pages"][0]["nodes"][node.id]["metadata"]["bound_image_source"]

    node.style["zoom"] = 2.0
    node.style["focus_x"] = 0.9
    second = inject_preview_image_urls(document.to_dict(), document)
    second_url = second["pages"][0]["nodes"][node.id]["metadata"]["bound_image_source"]

    assert first_url != second_url


def test_qt_host_registers_and_syncs_provider_before_main_qml_consumes_payload():
    source = Path(qt_host.__file__).read_text(encoding="utf-8")
    provider_index = source.index("engine.addImageProvider(PREVIEW_PROVIDER_NAME, preview_provider)")
    load_index = source.index("engine.load(QUrl.fromLocalFile")
    assert "preview_provider = create_live_scene_image_provider()" in source
    assert "preview_provider.sync_document(session.document)" in source
    assert "inject_preview_image_urls(router.payload(), session.document)" in source
    assert provider_index < load_index


def test_image_inspector_prefers_original_source_in_injected_payload():
    source = (Path(qt_host.__file__).with_name("qml") / "ImageInspector.qml").read_text(encoding="utf-8")
    assert "metadata.graphics2_preview_original_source || metadata.bound_image_source" in source


def test_live_provider_snapshot_can_be_replaced_after_undo_redo_style_document_swap(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QSize
    from PySide6.QtGui import QGuiApplication

    source = tmp_path / "source.png"
    PILImage.new("RGB", (400, 200), (220, 40, 40)).save(source)

    first_document, first_node = _document_with_image(str(source), width=120, height=80)
    provider = create_live_scene_image_provider()
    provider.sync_document(first_document)
    app = QGuiApplication.instance() or QGuiApplication([])
    app.processEvents()

    first = provider.requestImage(f"{first_node.id}/one", QSize(), QSize())
    assert first.width() == 120
    assert first.height() == 80

    second_document, _ = _document_with_image(
        str(source),
        node_id=first_node.id,
        width=240,
        height=100,
    )
    provider.sync_document(second_document)

    second = provider.requestImage(f"{first_node.id}/two", QSize(), QSize())
    assert second.width() == 240
    assert second.height() == 100


def test_live_provider_composes_cover_focus_and_crop_into_exact_target_size(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QSize
    from PySide6.QtGui import QGuiApplication

    source = tmp_path / "wide.png"
    PILImage.new("RGB", (600, 200), (30, 130, 220)).save(source)
    document, node = _document_with_image(str(source), width=180, height=180)
    node.style["crop"] = {"left": 0.1, "right": 0.1, "top": 0.0, "bottom": 0.0}
    node.style["flip_x"] = True
    provider = create_live_scene_image_provider()
    provider.sync_document(document)
    app = QGuiApplication.instance() or QGuiApplication([])
    app.processEvents()

    image = provider.requestImage(f"{node.id}/crop", QSize(), QSize())
    assert image.width() == 180
    assert image.height() == 180
    assert not image.isNull()
