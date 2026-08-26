from __future__ import annotations

"""Materialize promotion PPTX models calibrated for preprinted OFERTA paper.

The repository keeps the historical binary PPTX models intact.  The user's new
reference models differ mainly in DrawingML/layout XML.  To keep this change
reviewable through text-only repository tooling, the exact non-media package
parts from the approved references are stored as compressed text patches.  At
runtime we combine those approved XML parts with the packaged model media and
write a normal PPTX into a versioned per-user cache.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import zlib


PATCH_FORMAT = "srstudio-preprinted-offer-patch-1"
PATCH_SET = "preprinted-offer-v1"
PATCH_MODEL_NAMES = (
    "CARTAZ_VENDA.pptx",
    "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx",
    "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx",
    "CLUBE_EXCLUSIVO.pptx",
    "CLUBE_EXCLUSIVO_COM_LIMITE.pptx",
)


def preprinted_offer_patch_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "poster_templates" / "preprinted_offer_patches"


def preprinted_offer_cache_root() -> Path:
    return Path.home() / ".srstudio5" / "runtime-models" / PATCH_SET


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_patch(model_name: str) -> dict[str, object]:
    folder = preprinted_offer_patch_root() / model_name
    parts = sorted(folder.glob("part*.txt"))
    if not parts:
        raise FileNotFoundError(f"Patch do modelo não encontrado: {model_name}")
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in parts)
    try:
        payload = json.loads(zlib.decompress(base64.b64decode(encoded)).decode("utf-8"))
    except Exception as exc:  # pragma: no cover - corruption guard
        raise RuntimeError(f"Patch inválido para {model_name}: {exc}") from exc
    if payload.get("format") != PATCH_FORMAT or payload.get("model") != model_name:
        raise RuntimeError(f"Contrato de patch inválido para {model_name}.")
    return payload


def _patch_digest(payload: dict[str, object], source: Path) -> str:
    marker = json.dumps(
        {
            "patch_set": PATCH_SET,
            "target_visual_sha256": payload.get("target_visual_sha256"),
            "source_sha256": _sha256(source),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(marker).hexdigest()


def _write_patched_model(source: Path, destination: Path, payload: dict[str, object]) -> None:
    raw_parts = payload.get("parts")
    media_names = payload.get("media_names")
    if not isinstance(raw_parts, dict) or not isinstance(media_names, list):
        raise RuntimeError(f"Patch incompleto para {source.name}.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as original:
        source_names = set(original.namelist())
        missing_media = [str(name) for name in media_names if str(name) not in source_names]
        if missing_media:
            raise RuntimeError(
                f"Mídia histórica incompatível com {source.name}: {', '.join(missing_media)}"
            )

        with tempfile.NamedTemporaryFile(
            prefix=f".{source.stem}-",
            suffix=".pptx.tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)

        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for member, encoded in raw_parts.items():
                    try:
                        content = zlib.decompress(base64.b64decode(str(encoded)))
                    except Exception as exc:
                        raise RuntimeError(f"Parte OOXML inválida em {source.name}: {member}") from exc
                    target.writestr(str(member), content)

                for media_name in media_names:
                    name = str(media_name)
                    target.writestr(name, original.read(name))

                # Thumbnail is not part of the rendered slide but some Office builds
                # expect it when present in the historical package.
                if "docProps/thumbnail.jpeg" in source_names and "docProps/thumbnail.jpeg" not in raw_parts:
                    target.writestr("docProps/thumbnail.jpeg", original.read("docProps/thumbnail.jpeg"))

            with zipfile.ZipFile(temporary, "r") as check:
                bad = check.testzip()
                if bad is not None:
                    raise RuntimeError(f"PPTX materializado corrompido em {bad}.")
                required = {"ppt/presentation.xml", "ppt/slides/slide1.xml", "[Content_Types].xml"}
                if not required.issubset(check.namelist()):
                    raise RuntimeError(f"PPTX materializado incompleto: {source.name}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def materialize_preprinted_offer_models(source_root: str | Path) -> Path:
    """Return a complete model directory with the seven new promotion references.

    Wholesale and any unrelated model are copied byte-for-byte.  Promotion models
    listed in ``PATCH_MODEL_NAMES`` receive the approved preprinted-paper OOXML.
    """

    source = Path(source_root)
    if not source.is_dir():
        raise FileNotFoundError(source)

    cache = preprinted_offer_cache_root()
    cache.mkdir(parents=True, exist_ok=True)

    for source_model in sorted(source.glob("*.pptx")):
        destination = cache / source_model.name
        stamp = cache / f".{source_model.name}.sha256"

        if source_model.name in PATCH_MODEL_NAMES:
            payload = _load_patch(source_model.name)
            expected = _patch_digest(payload, source_model)
            current = stamp.read_text(encoding="ascii").strip() if stamp.is_file() else ""
            if destination.is_file() and current == expected:
                continue
            _write_patched_model(source_model, destination, payload)
            stamp.write_text(expected, encoding="ascii")
        else:
            expected = _sha256(source_model)
            current = stamp.read_text(encoding="ascii").strip() if stamp.is_file() else ""
            if destination.is_file() and current == expected and _sha256(destination) == expected:
                continue
            shutil.copy2(source_model, destination)
            stamp.write_text(expected, encoding="ascii")

    # Do not let removed packaged models survive forever in the cache.
    packaged_names = {path.name for path in source.glob("*.pptx")}
    for cached in cache.glob("*.pptx"):
        if cached.name not in packaged_names:
            cached.unlink(missing_ok=True)
            (cache / f".{cached.name}.sha256").unlink(missing_ok=True)

    return cache


__all__ = [
    "PATCH_MODEL_NAMES",
    "PATCH_SET",
    "materialize_preprinted_offer_models",
    "preprinted_offer_cache_root",
    "preprinted_offer_patch_root",
]
