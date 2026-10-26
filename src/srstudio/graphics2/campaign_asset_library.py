"""Local, validated catalog of promotional backgrounds and transparent seals.

The user imports a curated ZIP once. Artwork binaries live in the user data
directory, not the Git repository, and are only attached to a scene after
explicit selection. The reference PPTX and flattened posters are NOT artwork.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from zipfile import ZipFile

from .campaign_tools import CAMPAIGNS, local_campaign_path

PACK_FORMAT = "SRSTUDIO_CAMPAIGN_ARTWORK_1"
_MAX_IMAGE = 25 * 1024 * 1024
_MAX_TOTAL = 100 * 1024 * 1024
_MAX_RECORDS = 80
_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def campaign_library_root(root=None) -> Path:
    value = root or os.environ.get("SRSTUDIO_CAMPAIGN_ASSETS_DIR")
    return Path(value).expanduser().resolve() if value else (
        Path.home() / ".srstudio" / "campaign_artwork").resolve()


def list_campaign_assets(*, root=None) -> list[dict]:
    """List only installed artwork with existing local image files."""
    library = campaign_library_root(root)
    index = library / "catalog.json"
    if not index.exists():
        return []
    try:
        rows = json.loads(index.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            return []
        valid = []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            if entry.get("kind") not in ("background", "seal"):
                continue
            if entry.get("campaign_id") not in CAMPAIGNS:
                continue
            source = Path(str(entry.get("path") or "")).resolve()
            if not source.is_relative_to(library) or not source.is_file():
                continue
            valid.append({
                "id": str(entry.get("id") or ""),
                "campaign_id": entry["campaign_id"], "kind": entry["kind"],
                "name": str(entry.get("name") or source.name),
                "path": str(source),
            })
        return sorted(valid, key=lambda item: (item["campaign_id"], item["kind"], item["name"]))
    except (OSError, ValueError, TypeError):
        return []


def import_campaign_pack(source, *, root=None) -> dict:
    """Import only hash-verified images with constrained names and sizes.

    Invalid manifests leave the existing catalog untouched. References,
    products and PPTX never become backgrounds or seals by mistake.
    """
    archive = local_campaign_path(source)
    if not archive.is_file() or archive.suffix.lower() != ".zip":
        raise ValueError("Selecione um pacote ZIP de campanhas válido.")
    library = campaign_library_root(root)
    incoming: list[tuple[dict, bytes]] = []
    with ZipFile(archive, "r") as pack:
        manifest = json.loads(pack.read("manifest.json").decode("utf-8"))
        if not isinstance(manifest, dict) or manifest.get("format") != PACK_FORMAT:
            raise ValueError("Formato do catálogo promocional não reconhecido.")
        assets = manifest.get("assets")
        if not isinstance(assets, list) or len(assets) > _MAX_RECORDS:
            raise ValueError("Quantidade de arquivos no catálogo inválida.")
        total = 0
        for record in assets:
            if not isinstance(record, dict):
                raise ValueError("Item inválido no catálogo.")
            kind = str(record.get("kind") or "")
            if kind not in ("background", "seal"):
                continue
            campaign_id = str(record.get("campaign_id") or "")
            path_text = str(record.get("path") or "")
            name = PurePosixPath(path_text)
            expected_folder = "fundos" if kind == "background" else "selos"
            if (campaign_id not in CAMPAIGNS or len(name.parts) != 2
                    or name.parts[0] != expected_folder
                    or name.suffix.lower() not in _ALLOWED_EXT
                    or "\\" in path_text or ".." in name.parts):
                raise ValueError("Caminho de imagem do catálogo inválido.")
            item = pack.getinfo(path_text)
            expected_size = int(record.get("size") or -1)
            digest = str(record.get("sha256") or "").lower()
            if (not 0 < expected_size <= _MAX_IMAGE or
                    item.file_size != expected_size or
                    len(digest) != 64 or any(x not in "0123456789abcdef" for x in digest)):
                raise ValueError("Tamanho ou SHA-256 de imagem inválido.")
            total += expected_size
            if total > _MAX_TOTAL:
                raise ValueError("Pacote de campanhas excede o tamanho permitido.")
            content = pack.read(item)
            if sha256(content).hexdigest() != digest:
                raise ValueError("Arquivo do pacote não corresponde ao SHA-256 registrado.")
            incoming.append((record, content))

    # The catalog commit comes last. No invalid package changes existing entries.
    library.mkdir(parents=True, exist_ok=True)
    current = list_campaign_assets(root=library)
    # Existing records retain their paths and names; new entries overwrite by id.
    by_id = {entry["id"]: entry for entry in current if entry.get("id")}
    for record, content in incoming:
        digest = str(record["sha256"]).lower()
        dest = library / "files" / (digest[:24] + PurePosixPath(record["path"]).suffix.lower())
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or sha256(dest.read_bytes()).hexdigest() != digest:
            with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".campaign-", delete=False) as tmp:
                tmp.write(content)
                temp_name = tmp.name
            os.replace(temp_name, dest)
        key = f'{record["campaign_id"]}:{record["kind"]}:{digest[:24]}'
        by_id[key] = {
            "id": key, "campaign_id": record["campaign_id"],
            "kind": record["kind"], "name": str(record.get("name") or dest.stem),
            "path": str(dest),
        }
    index = library / "catalog.json"
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=library,
            prefix=".catalog-", suffix=".json", delete=False) as tmp:
        json.dump(list(by_id.values()), tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, index)
    return {"imported": len(incoming), "available": len(list_campaign_assets(root=library))}
