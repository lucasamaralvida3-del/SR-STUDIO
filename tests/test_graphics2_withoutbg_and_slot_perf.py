from __future__ import annotations

from pathlib import Path
import sys
import types

from PIL import Image

from srstudio.graphics2.background_removal import remove_product_background


def test_withoutbg_local_rgba_cache_and_model_reuse(tmp_path, monkeypatch):
    import srstudio.graphics2.background_removal as service
    monkeypatch.setattr(service, "_MODEL", None)
    calls = {"loaded": 0, "processed": 0}

    class FakeModel:
        def remove_background(self, source):
            calls["processed"] += 1
            image = Image.open(source).convert("RGBA")
            image.putalpha(0)
            return image

    class FakeWithoutBG:
        @staticmethod
        def open_weights():
            calls["loaded"] += 1
            return FakeModel()

    monkeypatch.setitem(sys.modules, "withoutbg", types.SimpleNamespace(WithoutBG=FakeWithoutBG))
    path = tmp_path / "product.jpg"
    Image.new("RGB", (32, 28), "white").save(path)
    cache = tmp_path / "cache"
    first = remove_product_background(path, cache_root=cache)
    second = remove_product_background(path, cache_root=cache)
    assert first == second
    assert first.suffix == ".png"
    assert calls == {"loaded": 1, "processed": 1}
    with Image.open(first) as result:
        assert result.mode == "RGBA"
        assert result.getchannel("A").getextrema() == (0, 0)
    assert path.read_bytes().startswith(b"\xff\xd8")


def test_transparent_product_skips_withoutbg_download(tmp_path, monkeypatch):
    import srstudio.graphics2.background_removal as service
    monkeypatch.setattr(service, "_MODEL", None)
    path = tmp_path / "ready.png"
    Image.new("RGBA", (14, 14), (10, 20, 30, 0)).save(path)
    assert remove_product_background(path, cache_root=tmp_path / "cache") == path
    assert service._MODEL is None


def test_qml_drags_dense_imports_without_rebinding_entire_scene():
    qml = Path("src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    fast = qml.split("function liveSlotNodeRect(node)", 1)[1].split("function clearSlotPreview()", 1)[0]
    assert fast.index("if (!activeSlotPreviewMembers[node.id])") < fast.index("var preview = activeSlotPreview")
    assert "Object.keys(ids).length > 24" in qml
    assert "visible: !smartSlotEditMode && anchorNode" in qml
    assert "sceneBridge.removeSlotBackground(chosenSlot)" in qml


def test_withoutbg_ui_controls_and_background_thread_bridge():
    inspector = Path("src/srstudio/graphics2/qml/ImageInspector.qml").read_text(encoding="utf-8")
    host = Path("src/srstudio/graphics2/qt_host.py").read_text(encoding="utf-8")
    assert "Remover fundo com withoutBG" in inspector
    assert "sceneBridge.removeBackground(targetId)" in inspector
    assert "threading.Thread(target=worker" in host
    assert "backgroundRemovalDone.emit" in host
    assert "def removeSlotBackground" in host
