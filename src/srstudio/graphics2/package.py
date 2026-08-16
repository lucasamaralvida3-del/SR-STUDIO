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
    """Salva um pacote portátil SR Scene 2 com assets e fontes do projeto.

    Fontes extraídas de PPTX/Canva são tratadas como recursos do documento e
    permanecem dentro do `.srscene`; elas não são instaladas no sistema.
    """

    assert_document_integrity(document)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() not in {".srscene", ".zip"}:
        target = target.with_suffix(".srscene")
    scene = document.to_dict()
    manifest: dict[str, Any] = {
        "format": PACKAGE_FORMAT,
        "schema": document.schema,
        "document_id": document.id,
        "assets": {},
        "fonts": [],
    }
    with NamedTemporaryFile(prefix=target.stem + ".", suffix=".tmp", dir=target.parent, delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            _write_assets(document, scene, manifest, archive, embed_local_assets=embed_local_assets)
            _write_fonts(scene, manifest, archive, embed_local_assets=embed_local_assets)
            scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            manifest["scene_sha256"] = sha256(scene_raw).hexdigest()
            archive.writestr("scene.json", scene_raw)
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return target


def load_package(path: str | Path, *, extract_assets_to: str | Path | None = None) -> GraphicsDocument:
    source = Path(path)
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != PACKAGE_FORMAT:
            raise ValueError("Pacote não é SR Graphics Engine 2")
        scene_raw = archive.read("scene.json")
        if sha256(scene_raw).hexdigest() != manifest.get("scene_sha256"):
            raise ValueError("Hash do scene.json inválido")
        document = GraphicsDocument.from_dict(json.loads(scene_raw.decode("utf-8")))
        if extract_assets_to:
            destination = Path(extract_assets_to)
            destination.mkdir(parents=True, exist_ok=True)
            _extract_assets(document, manifest, archive, destination)
            _extract_fonts(document, manifest, archive, destination / "fonts")
    assert_document_integrity(document)
    return document


def register_local_asset(
    document: GraphicsDocument,
    path: str | Path,
    *,
    kind: str = "image",
    mime: str = "",
) -> AssetRef:
    source = Path(path)
    raw = source.read_bytes()
    asset = AssetRef(kind=kind, source=str(source), mime=mime, sha256=sha256(raw).hexdigest())
    document.add_asset(asset)
    return asset


def _write_assets(
    document: GraphicsDocument,
    scene: dict[str, Any],
    manifest: dict[str, Any],
    archive: zipfile.ZipFile,
    *,
    embed_local_assets: bool,
) -> None:
    for asset_id, asset in document.assets.items():
        source = Path(asset.source) if asset.source else None
        stored = ""
        digest = asset.sha256
        if embed_local_assets and source and source.is_file():
            raw = source.read_bytes()
            digest = sha256(raw).hexdigest()
            suffix = source.suffix.lower() or ".bin"
            stored = f"assets/{asset_id}{suffix}"
            archive.writestr(stored, raw)
            scene["assets"][asset_id]["source"] = stored
            scene["assets"][asset_id]["embedded"] = True
            scene["assets"][asset_id]["sha256"] = digest
        manifest["assets"][asset_id] = {"sha256": digest, "stored": stored}


def _write_fonts(
    scene: dict[str, Any],
    manifest: dict[str, Any],
    archive: zipfile.ZipFile,
    *,
    embed_local_assets: bool,
) -> None:
    metadata = dict(scene.get("metadata") or {})
    entries = metadata.get("embedded_fonts")
    if not isinstance(entries, list):
        return
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            continue
        entry = raw_entry
        source_text = str(entry.get("extracted_path") or "").strip()
        source = Path(source_text) if source_text else None
        stored = ""
        digest = str(entry.get("sha256") or "")
        if embed_local_assets and source and source.is_file():
            raw = source.read_bytes()
            digest = sha256(raw).hexdigest()
            suffix = source.suffix.lower() or ".bin"
            family = _safe_name(str(entry.get("family") or "font"))
            style = _safe_name(str(entry.get("style") or "regular"))
            stored = f"fonts/{index:03d}-{family}-{style}-{digest[:12]}{suffix}"
            archive.writestr(stored, raw)
            entry["extracted_path"] = stored
            entry["embedded"] = True
            entry["sha256"] = digest
        manifest["fonts"].append(
            {
                "index": index,
                "family": str(entry.get("family") or ""),
                "style": str(entry.get("style") or ""),
                "sha256": digest,
                "stored": stored,
            }
        )


def _extract_assets(
    document: GraphicsDocument,
    manifest: dict[str, Any],
    archive: zipfile.ZipFile,
    destination: Path,
) -> None:
    for asset_id, meta in dict(manifest.get("assets") or {}).items():
        stored = str(meta.get("stored") or "")
        if not stored:
            continue
        raw = _read_verified_member(archive, stored, str(meta.get("sha256") or ""), f"asset {asset_id}")
        out = destination / Path(stored).name
        out.write_bytes(raw)
        if asset_id in document.assets:
            document.assets[asset_id].source = str(out)
            document.assets[asset_id].embedded = False
            document.assets[asset_id].sha256 = sha256(raw).hexdigest()


def _extract_fonts(
    document: GraphicsDocument,
    manifest: dict[str, Any],
    archive: zipfile.ZipFile,
    destination: Path,
) -> None:
    fonts = document.metadata.get("embedded_fonts")
    if not isinstance(fonts, list):
        return
    destination.mkdir(parents=True, exist_ok=True)
    for meta in list(manifest.get("fonts") or []):
        if not isinstance(meta, dict):
            continue
        stored = str(meta.get("stored") or "")
        if not stored:
            continue
        index = _as_int(meta.get("index"), default=-1)
        if index < 0 or index >= len(fonts) or not isinstance(fonts[index], dict):
            raise ValueError(f"Índice de fonte inválido no pacote: {index}")
        raw = _read_verified_member(archive, stored, str(meta.get("sha256") or ""), f"fonte {index}")
        out = destination / Path(stored).name
        out.write_bytes(raw)
        entry = fonts[index]
        entry["extracted_path"] = str(out)
        entry["embedded"] = False
        entry["sha256"] = sha256(raw).hexdigest()


def _read_verified_member(
    archive: zipfile.ZipFile,
    stored: str,
    expected_sha256: str,
    label: str,
) -> bytes:
    normalized = Path(stored)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"Caminho inválido para {label}: {stored}")
    try:
        raw = archive.read(stored)
    except KeyError as exc:
        raise ValueError(f"Recurso ausente no pacote para {label}: {stored}") from exc
    digest = sha256(raw).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(f"Hash inválido para {label}")
    return raw


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned.strip("-") or "resource"


def _as_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
