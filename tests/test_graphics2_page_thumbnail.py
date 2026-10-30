from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.qt_image_provider import create_live_scene_image_provider, inject_preview_image_urls


def test_thumbnail_renders_page_and_invalidates_only_changed_page():
    app = QGuiApplication.instance() or QGuiApplication([])
    document = GraphicsDocument()
    page = document.pages[0]
    page.background = "#ff0000"
    provider = create_live_scene_image_provider()
    provider.sync_document(document)
    payload = inject_preview_image_urls(document.to_dict(), document)
    url = payload["pages"][0]["thumbnail_url"]
    image = provider.requestImage(url.split("srscene/")[1], QSize(), QSize())
    assert image.pixelColor(10, 10).name() == "#ff0000"
    assert image.width() == 152
    cached = provider.requestImage(url.split("srscene/")[1], QSize(), QSize())
    assert cached.cacheKey() == image.cacheKey()
    page.background = "#0000ff"
    provider.sync_document(document)
    changed = inject_preview_image_urls(document.to_dict(), document)["pages"][0]["thumbnail_url"]
    assert changed != url
    image = provider.requestImage(changed.split("srscene/")[1], QSize(), QSize())
    assert image.pixelColor(10, 10).name() == "#0000ff"
