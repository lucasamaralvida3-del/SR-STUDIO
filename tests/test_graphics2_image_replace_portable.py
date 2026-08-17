from __future__ import annotations

import os

import pytest

from srstudio.graphics2.image_replace import replace_image_source
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.qt_renderer import render_png


def test_replaced_image_survives_embedded_save_after_original_file_is_removed(tmp_path):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QColor, QGuiApplication, QImage

    app = QGuiApplication.instance() or QGuiApplication([])
    source = tmp_path / "manual-product.png"
    image = QImage(80, 60, QImage.Format_ARGB32)
    image.fill(QColor(210, 30, 40))
    assert image.save(str(source), "PNG")

    document = GraphicsDocument(name="Portable image override")
    page = document.active_page
    page.width = 300
    page.height = 220
    node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        transform=Transform(x=50, y=40, width=160, height=120),
        style={"fit": "contain"},
    )
    page.add_node(node)
    session = GraphicsSession(document)
    replace_image_source(session, node.id, source.as_uri())

    package = tmp_path / "portable.srscene"
    save_package(session.document, package, embed_local_assets=True)
    source.unlink()
    assert not source.exists()

    reopened = load_package(package, extract_assets_to=tmp_path / "portable-assets")
    reopened_node = reopened.active_page.node(node.id)
    assert reopened_node is not None
    asset = reopened.assets[reopened_node.asset_id]
    assert asset.embedded is True
    assert asset.source
    assert os.path.isfile(asset.source)

    output = tmp_path / "portable-render.png"
    report = render_png(reopened, output, target_width=300)
    app.processEvents()
    assert report.ok
    assert output.is_file()
    rendered = QImage(str(output))
    assert not rendered.isNull()
    center = rendered.pixelColor(130, 100)
    assert center.red() > 150
    assert center.green() < 100
    assert center.blue() < 100
