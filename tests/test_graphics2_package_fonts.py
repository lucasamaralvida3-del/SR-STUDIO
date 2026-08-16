from __future__ import annotations

import json
import zipfile
from hashlib import sha256
from pathlib import Path

from srstudio.graphics2.model import AssetRef, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.package import load_package, save_package


def test_srscene_embeds_and_restores_project_fonts(tmp_path):
    font = tmp_path / "Anton.ttf"
    font.write_bytes(b"FAKE-SFNT-FOR-PACKAGE-ROUNDTRIP")
    digest = sha256(font.read_bytes()).hexdigest()

    document = GraphicsDocument(name="Portable Fonts")
    document.metadata["embedded_fonts"] = [
        {
            "family": "Anton",
            "style": "regular",
            "extracted_path": str(font),
            "sha256": digest,
            "runtime_allowed": True,
        }
    ]

    package = save_package(document, tmp_path / "portable.srscene")
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        scene = json.loads(archive.read("scene.json").decode("utf-8"))
        assert len(manifest["fonts"]) == 1
        stored = manifest["fonts"][0]["stored"]
        assert stored.startswith("fonts/")
        assert archive.read(stored) == font.read_bytes()
        assert scene["metadata"]["embedded_fonts"][0]["extracted_path"] == stored
        assert scene["metadata"]["embedded_fonts"][0]["embedded"] is True

    restored = load_package(package, extract_assets_to=tmp_path / "extracted")
    restored_entry = restored.metadata["embedded_fonts"][0]
    restored_font = Path(restored_entry["extracted_path"])
    assert restored_font.is_file()
    assert restored_font.read_bytes() == font.read_bytes()
    assert restored_entry["embedded"] is False
    assert restored_entry["sha256"] == digest


def test_srscene_keeps_font_metadata_when_embedding_is_disabled(tmp_path):
    font = tmp_path / "HighCruiser.otf"
    font.write_bytes(b"LOCAL-FONT")
    document = GraphicsDocument(name="External Font")
    document.metadata["embedded_fonts"] = [
        {
            "family": "High Cruiser",
            "style": "regular",
            "extracted_path": str(font),
            "sha256": sha256(font.read_bytes()).hexdigest(),
            "runtime_allowed": True,
        }
    ]

    package = save_package(document, tmp_path / "external.srscene", embed_local_assets=False)
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        scene = json.loads(archive.read("scene.json").decode("utf-8"))
        assert manifest["fonts"][0]["stored"] == ""
        assert scene["metadata"]["embedded_fonts"][0]["extracted_path"] == str(font)


def test_srscene_rebinds_image_nodes_to_extracted_asset_path(tmp_path):
    image = tmp_path / "produto.png"
    image.write_bytes(b"PNG-PAYLOAD-FOR-PACKAGE-TEST")
    document = GraphicsDocument(name="Portable Image")
    asset = AssetRef(
        kind="image",
        source=str(image),
        sha256=sha256(image.read_bytes()).hexdigest(),
    )
    document.add_asset(asset)
    node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        asset_id=asset.id,
        transform=Transform(x=10, y=10, width=100, height=100),
        metadata={"bound_image_source": str(image)},
    )
    document.active_page.add_node(node)

    package = save_package(document, tmp_path / "portable-image.srscene")
    image.unlink()
    restored = load_package(package, extract_assets_to=tmp_path / "runtime-assets")
    restored_node = restored.active_page.node(node.id)
    restored_asset = restored.assets[asset.id]

    assert restored_node is not None
    assert Path(restored_asset.source).is_file()
    assert restored_node.metadata["bound_image_source"] == restored_asset.source
    assert restored_node.metadata["package_asset_extracted"] is True
