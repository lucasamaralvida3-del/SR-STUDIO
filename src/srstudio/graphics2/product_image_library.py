from __future__ import annotations

"""Permanent per-user catalog of product pictures, indexed by stable product ID.

The original source may live in Downloads or a removable drive; store a content-
addressed copy in the user's application data, outside disposable build folders.
The JSON index is atomically replaced and always regenerated from safe values.
"""

from hashlib import sha256
from pathlib import Path
from threading import RLock
import json
import os
import shutil
import tempfile

from .image_replace import normalize_local_image_source

_LOCK = RLock()
MAX_IMAGE_BYTES = 50 * 1024 * 1024


def library_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / ".local" / "share")
    return Path(base).expanduser() / "SRStudio" / "ProductImages"


def _product_id(product_id: object) -> str:
    result = str(product_id or "").strip()
    if not result or len(result) > 250:
        raise ValueError("Produto sem ID/código válido para vincular imagem.")
    return result


def _index_path(root: Path) -> Path:
    return root / "products.json"


def _read_index(root: Path) -> dict:
    path = _index_path(root)
    if not path.exists():
        return {}
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Índice de imagens dos produtos está inválido.")
    return result


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".products-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def store_product_image(
    product_id: str,
    product_name: str,
    source: str,
    *,
    root: Path | None = None,
) -> dict[str, str]:
    """Copy and link one validated image. Never store the source's basename as a key."""
    product_id = _product_id(product_id)
    source_path = normalize_local_image_source(source)
    if source_path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Imagem muito grande (limite 50 MB).")
    from PIL import Image

    with Image.open(source_path) as image:
        image.verify()
    digest = sha256()
    with source_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    root = Path(root) if root is not None else library_root()
    image_dir = root / "files"
    target = image_dir / (digest.hexdigest() + source_path.suffix.lower())
    with _LOCK:
        image_dir.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            fd, tmpname = tempfile.mkstemp(prefix=".import-", suffix=".tmp", dir=image_dir)
            os.close(fd)
            try:
                shutil.copyfile(source_path, tmpname)
                if sha256(Path(tmpname).read_bytes()).hexdigest() != digest.hexdigest():
                    raise OSError("Arquivo copiado apresentou falha de integridade.")
                os.replace(tmpname, target)
            finally:
                if os.path.exists(tmpname):
                    os.unlink(tmpname)
        records = _read_index(root)
        entry = {"product_id": product_id, "name": str(product_name or "").strip(),
                 "image_path": str(target.resolve()), "sha256": digest.hexdigest()}
        records[product_id] = entry
        _atomic_json(_index_path(root), records)
    return entry


def store_product_images_batch(requests: list[dict], *, root: Path | None = None) -> list[dict]:
    """Persist an explicitly confirmed batch after validating every source."""
    from PIL import Image

    if not requests or len(requests) > 100:
        raise ValueError("Selecione entre 1 e 100 imagens para revisão em lote.")
    seen: set[str] = set()
    prepared = []
    for request in requests:
        product_id = _product_id(request.get("product_id"))
        if product_id in seen:
            raise ValueError("O mesmo código aparece duas vezes na revisão em lote.")
        seen.add(product_id)
        source = normalize_local_image_source(str(request.get("image_path") or ""))
        if source.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("Imagem muito grande (limite 50 MB).")
        with Image.open(source) as image:
            image.verify()
        prepared.append((product_id, str(request.get("name") or ""), str(source)))
    return [store_product_image(product_id, name, source, root=root)
            for product_id, name, source in prepared]


def read_product_links(*, root: Path | None = None) -> dict[str, dict]:
    root = Path(root) if root is not None else library_root()
    with _LOCK:
        links = _read_index(root)
    return {k: v for k, v in links.items() if isinstance(v, dict)
            and isinstance(v.get("image_path"), str)
            and Path(v["image_path"]).is_file()}


def apply_stored_product_links(document, *, root: Path | None = None) -> int:
    """Hydrate product thumbnails after relaunch/import; retain each item's own name."""
    records = read_product_links(root=root)
    from .image_suggestions import approved_link_compatible
    products = document.metadata.get("products") or []
    changed = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        key = str(product.get("id") or product.get("product_id") or "").strip()
        entry = records.get(key)
        if (entry is not None and approved_link_compatible(product, entry)
                and product.get("image_path") != entry["image_path"]):
            product["image_path"] = entry["image_path"]
            product["image"] = entry["image_path"]
            product["image_linked_by"] = "product_id"
            changed += 1
    return changed


def attach_image_to_document(document, product_id: str, entry: dict) -> bool:
    """Update the in-memory product catalog after the background copy finishes."""
    product_id = _product_id(product_id)
    updated = False
    for product in document.metadata.get("products") or []:
        if isinstance(product, dict) and str(product.get("id") or product.get("product_id") or "").strip() == product_id:
            product["image_path"] = entry["image_path"]
            product["image"] = entry["image_path"]
            product["image_linked_by"] = "product_id"
            updated = True
    return updated
