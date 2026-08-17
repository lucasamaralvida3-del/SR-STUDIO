from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import zipfile

import pytest

from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.package import PACKAGE_FORMAT, load_package, save_package


def _rewrite_package(source: Path, target: Path, mutate_manifest=None, mutate_scene=None) -> Path:
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        scene = json.loads(archive.read("scene.json").decode("utf-8"))
        extra = {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
            if info.filename not in {"manifest.json", "scene.json"}
        }
    if mutate_scene:
        mutate_scene(scene)
    scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    manifest["scene_sha256"] = sha256(scene_raw).hexdigest()
    if mutate_manifest:
        mutate_manifest(manifest)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in extra.items():
            archive.writestr(name, raw)
        archive.writestr("scene.json", scene_raw)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8"))
    return target


def test_package_round_trip_stays_valid(tmp_path: Path):
    document = GraphicsDocument(name="Encarte teste")
    target = save_package(document, tmp_path / "encarte.srscene", embed_local_assets=False)

    restored = load_package(target)

    assert restored.id == document.id
    assert restored.name == "Encarte teste"
    assert restored.schema == "srscene/2.0"


def test_load_rejects_truncated_or_non_zip_package(tmp_path: Path):
    target = tmp_path / "broken.srscene"
    target.write_bytes(b"not-a-zip")

    with pytest.raises(ValueError, match="corrompido|truncado"):
        load_package(target)


def test_load_rejects_missing_required_scene_member(tmp_path: Path):
    target = tmp_path / "missing-scene.srscene"
    manifest = {"format": PACKAGE_FORMAT, "schema": "srscene/2.0", "document_id": "doc", "scene_sha256": ""}
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))

    with pytest.raises(ValueError, match="scene.json"):
        load_package(target)


def test_load_rejects_manifest_document_id_mismatch(tmp_path: Path):
    original = save_package(GraphicsDocument(name="Original"), tmp_path / "original.srscene", embed_local_assets=False)
    tampered = _rewrite_package(
        original,
        tmp_path / "tampered-id.srscene",
        mutate_manifest=lambda manifest: manifest.__setitem__("document_id", "different-document"),
    )

    with pytest.raises(ValueError, match="ID do documento"):
        load_package(tampered)


def test_load_rejects_manifest_schema_mismatch(tmp_path: Path):
    original = save_package(GraphicsDocument(), tmp_path / "original.srscene", embed_local_assets=False)
    tampered = _rewrite_package(
        original,
        tmp_path / "tampered-schema.srscene",
        mutate_manifest=lambda manifest: manifest.__setitem__("schema", "srscene/999"),
    )

    with pytest.raises(ValueError, match="Schema do manifesto"):
        load_package(tampered)


def test_load_rejects_duplicate_required_members(tmp_path: Path):
    target = tmp_path / "duplicates.srscene"
    scene = GraphicsDocument().to_dict()
    scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    manifest = {
        "format": PACKAGE_FORMAT,
        "schema": "srscene/2.0",
        "document_id": scene["id"],
        "scene_sha256": sha256(scene_raw).hexdigest(),
        "assets": {},
        "fonts": [],
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("scene.json", scene_raw)
        archive.writestr("scene.json", scene_raw)
        archive.writestr("manifest.json", json.dumps(manifest))

    with pytest.raises(ValueError, match="duplicados"):
        load_package(target)


def test_load_rejects_unsafe_archive_member_paths(tmp_path: Path):
    target = tmp_path / "unsafe.srscene"
    scene = GraphicsDocument().to_dict()
    scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    manifest = {
        "format": PACKAGE_FORMAT,
        "schema": "srscene/2.0",
        "document_id": scene["id"],
        "scene_sha256": sha256(scene_raw).hexdigest(),
        "assets": {},
        "fonts": [],
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("scene.json", scene_raw)
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("../outside.txt", b"unsafe")

    with pytest.raises(ValueError, match="Caminho inválido"):
        load_package(target)
