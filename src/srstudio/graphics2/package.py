from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
import json
import os
import zipfile

from .model import AssetRef, GraphicsDocument
from .preflight import assert_document_integrity

PACKAGE_FORMAT = "SR_GRAPHICS_PACKAGE_2"


def save_package(document: GraphicsDocument, path: str | Path, *, embed_local_assets: bool = True) -> Path:
    assert_document_integrity(document)
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {".srscene", ".zip"}: target = target.with_suffix(".srscene")
    scene = document.to_dict()
    manifest: dict[str, Any] = {"format": PACKAGE_FORMAT, "schema": document.schema, "document_id": document.id, "assets": {}}
    with NamedTemporaryFile(prefix=target.stem + ".", suffix=".tmp", dir=target.parent, delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for asset_id, asset in document.assets.items():
                source = Path(asset.source) if asset.source else None; stored = ""; digest = asset.sha256
                if embed_local_assets and source and source.is_file():
                    raw = source.read_bytes(); digest = sha256(raw).hexdigest(); stored = f"assets/{asset_id}{source.suffix.lower()}"
                    archive.writestr(stored, raw); scene["assets"][asset_id]["source"] = stored; scene["assets"][asset_id]["embedded"] = True; scene["assets"][asset_id]["sha256"] = digest
                manifest["assets"][asset_id] = {"sha256": digest, "stored": stored}
            scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            manifest["scene_sha256"] = sha256(scene_raw).hexdigest(); archive.writestr("scene.json", scene_raw)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        os.replace(temp_path, target)
    finally:
        if temp_path.exists(): temp_path.unlink(missing_ok=True)
    return target


def load_package(path: str | Path, *, extract_assets_to: str | Path | None = None) -> GraphicsDocument:
    source = Path(path)
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != PACKAGE_FORMAT: raise ValueError("Pacote não é SR Graphics Engine 2")
        scene_raw = archive.read("scene.json")
        if sha256(scene_raw).hexdigest() != manifest.get("scene_sha256"): raise ValueError("Hash do scene.json inválido")
        document = GraphicsDocument.from_dict(json.loads(scene_raw.decode("utf-8")))
        if extract_assets_to:
            destination = Path(extract_assets_to); destination.mkdir(parents=True, exist_ok=True)
            for asset_id, meta in dict(manifest.get("assets") or {}).items():
                stored = str(meta.get("stored") or "")
                if not stored: continue
                raw = archive.read(stored); digest = sha256(raw).hexdigest()
                if meta.get("sha256") and digest != meta.get("sha256"): raise ValueError(f"Hash inválido para asset {asset_id}")
                out = destination / Path(stored).name; out.write_bytes(raw)
                if asset_id in document.assets:
                    document.assets[asset_id].source = str(out); document.assets[asset_id].embedded = False; document.assets[asset_id].sha256 = digest
    assert_document_integrity(document); return document


def register_local_asset(document: GraphicsDocument, path: str | Path, *, kind: str = "image", mime: str = "") -> AssetRef:
    source = Path(path); raw = source.read_bytes()
    asset = AssetRef(kind=kind, source=str(source), mime=mime, sha256=sha256(raw).hexdigest()); document.add_asset(asset); return asset
