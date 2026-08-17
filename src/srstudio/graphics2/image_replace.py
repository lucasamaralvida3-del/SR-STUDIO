from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
import os

from .model import AssetRef, NodeKind
from .operations import GraphicsSession

_SUPPORTED_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}


@dataclass(slots=True, frozen=True)
class ImageReplacement:
    node_id: str
    asset_id: str
    source: str
    reused_asset: bool


def normalize_local_image_source(raw_source: str) -> Path:
    """Converte caminho local ou URL ``file://`` do QML em ``Path`` absoluto."""

    raw = str(raw_source or "").strip()
    if not raw:
        raise ValueError("Nenhuma imagem foi selecionada.")

    is_windows_drive = (
        len(raw) >= 3
        and raw[0].isalpha()
        and raw[1] == ":"
        and raw[2] in {"\\", "/"}
    )
    is_unc_path = raw.startswith("\\\\")

    if is_windows_drive or is_unc_path:
        value = raw
    else:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.scheme.lower() != "file":
            raise ValueError("A substituição de imagem aceita somente arquivos locais.")

        if parsed.scheme.lower() == "file":
            if parsed.netloc and parsed.netloc not in {"", "localhost"}:
                # UNC: file://server/share/file.png
                value = f"//{parsed.netloc}{unquote(parsed.path)}"
            else:
                value = unquote(parsed.path)
            if os.name == "nt" and len(value) >= 3 and value[0] == "/" and value[2] == ":":
                value = value[1:]
        else:
            value = raw

    path = Path(value).expanduser()
    try:
        path = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Imagem não encontrada: {path}") from exc
    if not path.is_file():
        raise ValueError(f"O caminho não aponta para uma imagem válida: {path}")
    if path.suffix.lower() not in _SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(
            "Formato de imagem não suportado. Use PNG, JPG/JPEG, WebP, BMP, GIF ou TIFF."
        )
    return path


def replace_image_source(session: GraphicsSession, node_id: str, raw_source: str) -> ImageReplacement:
    """Troca somente a fonte visual de uma imagem, preservando o design do nó.

    A operação mantém o mesmo ``node_id`` — portanto ProductCard/SmartSlot não
    precisam ser reconstruídos — e não toca em transform, crop, rotação,
    opacidade ou z-order. O histórico da sessão captura asset + metadata para
    undo/redo atômico.
    """

    node = session.page.node(str(node_id or ""))
    if node is None or node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
        raise ValueError("Selecione uma imagem editável para substituir.")
    if session.effective_locked(node.id):
        raise ValueError("A imagem está bloqueada.")

    path = normalize_local_image_source(raw_source)
    canonical = str(path)
    existing = next(
        (
            asset
            for asset in session.document.assets.values()
            if _same_local_source(asset.source, canonical)
        ),
        None,
    )
    reused = existing is not None

    with session.transaction("Substituir imagem"):
        asset = existing
        if asset is None:
            asset = AssetRef(
                kind="image",
                source=canonical,
                embedded=False,
                metadata={"source": "manual-image-replace"},
            )
            session.document.assets[asset.id] = asset
        node.asset_id = asset.id
        node.metadata["bound_image_source"] = canonical
        node.metadata["manual_image_override"] = True
        node.visible = True

    return ImageReplacement(
        node_id=node.id,
        asset_id=asset.id,
        source=canonical,
        reused_asset=reused,
    )


def _same_local_source(left: str, right: str) -> bool:
    if not left:
        return False
    try:
        left_path = Path(str(left)).expanduser().resolve()
        right_path = Path(str(right)).expanduser().resolve()
    except (OSError, RuntimeError):
        return str(left) == str(right)
    if os.name == "nt":
        return os.path.normcase(str(left_path)) == os.path.normcase(str(right_path))
    return left_path == right_path
