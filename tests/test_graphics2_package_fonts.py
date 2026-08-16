from __future__ import annotations

import json
import zipfile
from hashlib import sha256
from pathlib import Path

from srstudio.graphics2.model import GraphicsDocument
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
