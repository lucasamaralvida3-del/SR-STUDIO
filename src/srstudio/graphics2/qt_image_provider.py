from __future__ import annotations

"""Provider de imagens do canvas Qt Quick com a mesma geometria do renderer.

O GraphicsEditor original usa ``Image.PreserveAspectFit/Crop`` e, por isso,
não consegue representar sozinho ``zoom + focus_x + focus_y``. Em vez de
duplicar mais lógica dentro do QML principal, este módulo entrega ao canvas uma
imagem já composta no aspect ratio exato do node. O documento SR Scene nunca é
alterado: apenas o payload de preview recebe URLs ``image://srscene/...``.

QQuickImageProvider pode atender requests fora da thread da UI. Por isso o
provider não toca no ``GraphicsSession`` durante ``requestImage``: a UI publica
snapshots imutáveis por ``sync_document`` e o worker consome somente cópias sob
lock. Undo/redo e edições continuam atualizando o preview sem corrida de dados.
"""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import unquote, urlparse
import json
import re

from .image_crop import crop_pixel_box
from .model import GraphicsDocument, GraphicsNode, NodeKind

PREVIEW_PROVIDER_NAME = "srscene"


def inject_preview_image_urls(scene: dict[str, Any], document: GraphicsDocument) -> dict[str, Any]:
    """Troca somente a origem visual do payload por URLs do provider Qt.

    ``graphics2_preview_original_source`` mantém a origem verdadeira disponível
    para ferramentas como ImageInspector, exportação e diagnóstico. Como
    ``router.payload()`` já devolve uma cópia serializada, a mutação é segura.
    """

    assets = scene.get("assets") if isinstance(scene.get("assets"), dict) else {}
    for page in scene.get("pages") or []:
        nodes = page.get("nodes") if isinstance(page, dict) else None
        if not isinstance(nodes, dict):
            continue
        for node in nodes.values():
            if not isinstance(node, dict) or str(node.get("kind") or "") not in {"image", "background"}:
                continue
            metadata = node.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                node["metadata"] = metadata
            original = _serialized_source(node, metadata, assets)
            if not original:
                continue
            metadata["graphics2_preview_original_source"] = original
            signature = _preview_signature(node, original)
            metadata["bound_image_source"] = f"image://{PREVIEW_PROVIDER_NAME}/{node.get('id')}/{signature}"
    return scene


def create_live_scene_image_provider():
    """Cria um QQuickImageProvider baseado em snapshots sincronizados pela UI."""

    try:
        from PySide6 import QtCore, QtGui
        from PySide6.QtQml import QQmlImageProviderBase
        from PySide6.QtQuick import QQuickImageProvider
    except Exception as exc:  # pragma: no cover - validado no job Qt/Windows
        raise RuntimeError("Provider de preview do Graphics Engine 2 requer PySide6.") from exc

    image_type = (
        QQmlImageProviderBase.ImageType.Image
        if hasattr(QQmlImageProviderBase, "ImageType")
        else QQmlImageProviderBase.Image
    )

    class LiveSceneImageProvider(QQuickImageProvider):
        def __init__(self) -> None:
            super().__init__(image_type)
            self._lock = RLock()
            self._nodes: dict[str, dict[str, Any]] = {}

        def sync_document(self, document: GraphicsDocument) -> None:
            snapshot: dict[str, dict[str, Any]] = {}
            for page in document.pages:
                for node in page.nodes.values():
                    if node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
                        continue
                    source = _model_source(document, node)
                    if not source:
                        continue
                    snapshot[node.id] = {
                        "source": source,
                        "width": float(node.transform.width or 1.0),
                        "height": float(node.transform.height or 1.0),
                        "style": deepcopy(node.style),
                        "clip_path": deepcopy(node.metadata.get("clip_path")),
                    }
            with self._lock:
                self._nodes = snapshot

        def requestImage(self, image_id, size, requested_size):  # noqa: N802 - contrato Qt
            node_id = str(image_id or "").split("/", 1)[0]
            with self._lock:
                raw = self._nodes.get(node_id)
                spec = deepcopy(raw) if raw is not None else None
            if spec is None:
                return _transparent_image(QtGui, 1, 1)

            local = _local_path(str(spec.get("source") or ""), QtCore)
            if local is None or not local.is_file():
                return _transparent_image(QtGui, 1, 1)
            image = QtGui.QImage(str(local))
            if image.isNull():
                return _transparent_image(QtGui, 1, 1)
            style = dict(spec.get("style") or {})
            image = _apply_crop(image, dict(style.get("crop") or {}), QtCore)
            width, height = _target_size(spec, requested_size)
            composed = _compose(
                image,
                width,
                height,
                style,
                QtCore,
                QtGui,
                clip_path=spec.get("clip_path"),
            )
            try:
                size.setWidth(composed.width())
                size.setHeight(composed.height())
            except Exception:
                pass
            return composed

    return LiveSceneImageProvider()


def _serialized_source(node: dict[str, Any], metadata: dict[str, Any], assets: dict[str, Any]) -> str:
    original = str(metadata.get("graphics2_preview_original_source") or "")
    if original:
        return original
    bound = str(metadata.get("bound_image_source") or "")
    if bound and not bound.startswith(f"image://{PREVIEW_PROVIDER_NAME}/"):
        return bound
    source_url = str(metadata.get("source_url") or "")
    if source_url:
        return source_url
    asset_id = str(node.get("asset_id") or "")
    asset = assets.get(asset_id) if asset_id else None
    return str(asset.get("source") or "") if isinstance(asset, dict) else ""


def _preview_signature(node: dict[str, Any], source: str) -> str:
    style = dict(node.get("style") or {})
    transform = dict(node.get("transform") or {})
    metadata = dict(node.get("metadata") or {})
    payload = {
        "source": source,
        "source_revision": _source_revision(source),
        "asset_id": node.get("asset_id"),
        "width": transform.get("width"),
        "height": transform.get("height"),
        "fit": style.get("fit"),
        "zoom": style.get("zoom"),
        "focus_x": style.get("focus_x"),
        "focus_y": style.get("focus_y"),
        "flip_x": style.get("flip_x"),
        "flip_y": style.get("flip_y"),
        "crop": style.get("crop"),
        "clip_path": metadata.get("clip_path"),
    }
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _source_revision(source: str) -> str:
    """Invalida cache do QML quando um arquivo é sobrescrito no mesmo caminho."""

    text = str(source or "").strip()
    if not text or text.startswith(("http://", "https://", "data:")):
        return ""
    raw = text
    parsed = urlparse(text)
    if parsed.scheme.lower() == "file":
        raw = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", raw):
            raw = raw[1:]
    elif parsed.scheme and not re.match(r"^[A-Za-z]:[\\/]", text):
        return ""
    try:
        stat = Path(raw).stat()
    except OSError:
        return ""
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def _model_source(document: GraphicsDocument, node: GraphicsNode) -> str:
    metadata = node.metadata or {}
    bound = str(metadata.get("bound_image_source") or "")
    if bound and not bound.startswith(f"image://{PREVIEW_PROVIDER_NAME}/"):
        return bound
    source_url = str(metadata.get("source_url") or "")
    if source_url:
        return source_url
    asset = document.assets.get(node.asset_id) if node.asset_id else None
    return str(asset.source or "") if asset is not None else ""


def _local_path(source: str, QtCore) -> Path | None:
    text = str(source or "").strip()
    if not text or text.startswith(("http://", "https://", "data:")):
        return None
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return Path(text)
    url = QtCore.QUrl(text)
    if url.isLocalFile():
        return Path(url.toLocalFile())
    if not url.scheme():
        return Path(text)
    return None


def _target_size(spec: dict[str, Any], requested_size) -> tuple[int, int]:
    width = max(1, round(float(spec.get("width") or 1.0)))
    height = max(1, round(float(spec.get("height") or 1.0)))
    try:
        requested_w = int(requested_size.width())
        requested_h = int(requested_size.height())
    except Exception:
        requested_w = requested_h = -1
    if requested_w > 0 and requested_h > 0:
        width, height = requested_w, requested_h
    max_side = 4096
    if width > max_side or height > max_side:
        scale = min(max_side / width, max_side / height)
        width = max(1, round(width * scale))
        height = max(1, round(height * scale))
    return width, height


def _transparent_image(QtGui, width: int, height: int):
    image = QtGui.QImage(max(1, width), max(1, height), QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    return image


def _apply_crop(image, crop: dict[str, Any], QtCore):
    if not crop:
        return image
    x, y, width, height = crop_pixel_box(image.width(), image.height(), crop)
    if x == 0 and y == 0 and width == image.width() and height == image.height():
        return image
    return image.copy(QtCore.QRect(x, y, width, height))


def _custom_clip_path(
    spec: object,
    width: int,
    height: int,
    QtCore,
    QtGui,
    *,
    mirror_x: bool = False,
    mirror_y: bool = False,
):
    """Converte ``custom_path`` DrawingML para máscara local do preview.

    O QML ainda aplica ``mirror``/``mirrorVertically`` depois que a imagem sai
    do provider. Por isso a máscara é pré-espelhada aqui: após o espelhamento do
    Item, o contorno visual volta à orientação original, igual ao QPainter de
    produção que espelha somente a fotografia e mantém a forma do template.
    """

    if not isinstance(spec, dict):
        return None
    paths = list(spec.get("paths") or [])
    if not paths:
        return None
    result = QtGui.QPainterPath()
    target_w = float(max(1, width))
    target_h = float(max(1, height))

    for item in paths:
        if not isinstance(item, dict):
            continue
        source_w = max(1e-9, float(item.get("width") or spec.get("width") or 0.0))
        source_h = max(1e-9, float(item.get("height") or spec.get("height") or 0.0))
        sx = target_w / source_w
        sy = target_h / source_h

        def point(raw):
            x = float(raw[0]) * sx
            y = float(raw[1]) * sy
            if mirror_x:
                x = target_w - x
            if mirror_y:
                y = target_h - y
            return QtCore.QPointF(x, y)

        for command in item.get("commands") or []:
            if not isinstance(command, dict):
                continue
            op = str(command.get("op") or "")
            points = list(command.get("points") or [])
            if op == "M" and points:
                result.moveTo(point(points[0]))
            elif op == "L" and points:
                result.lineTo(point(points[0]))
            elif op == "C" and len(points) >= 3:
                result.cubicTo(point(points[0]), point(points[1]), point(points[2]))
            elif op == "Q" and len(points) >= 2:
                result.quadTo(point(points[0]), point(points[1]))
            elif op == "Z":
                result.closeSubpath()
    return result if not result.isEmpty() else None


def _compose(
    image,
    width: int,
    height: int,
    style: dict[str, Any],
    QtCore,
    QtGui,
    *,
    clip_path: object = None,
):
    target = _transparent_image(QtGui, width, height)
    painter = QtGui.QPainter(target)
    if not painter.isActive():
        return target
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
    try:
        flip_x = bool(style.get("flip_x"))
        flip_y = bool(style.get("flip_y"))
        clip = _custom_clip_path(
            clip_path,
            width,
            height,
            QtCore,
            QtGui,
            mirror_x=flip_x,
            mirror_y=flip_y,
        )
        if clip is not None:
            painter.setClipPath(clip)

        fit = str(style.get("fit") or "contain").lower()
        focus_x = min(1.0, max(0.0, float(style.get("focus_x", 0.5) or 0.5)))
        focus_y = min(1.0, max(0.0, float(style.get("focus_y", 0.5) or 0.5)))
        if flip_x:
            focus_x = 1.0 - focus_x
        if flip_y:
            focus_y = 1.0 - focus_y
        zoom = max(0.05, float(style.get("zoom", 1.0) or 1.0))
        full_target = QtCore.QRectF(0.0, 0.0, float(width), float(height))
        if fit == "fill":
            painter.drawImage(full_target, image)
            return target

        iw, ih = float(max(1, image.width())), float(max(1, image.height()))
        tw, th = float(max(1, width)), float(max(1, height))
        if fit == "cover" or zoom > 1.0001:
            scale = max(tw / iw, th / ih) * zoom
            source_w = min(iw, tw / max(scale, 1e-9))
            source_h = min(ih, th / max(scale, 1e-9))
            source_x = (iw - source_w) * focus_x
            source_y = (ih - source_h) * focus_y
            painter.drawImage(full_target, image, QtCore.QRectF(source_x, source_y, source_w, source_h))
            return target

        scale = min(tw / iw, th / ih)
        draw_w, draw_h = iw * scale, ih * scale
        dest = QtCore.QRectF((tw - draw_w) * focus_x, (th - draw_h) * focus_y, draw_w, draw_h)
        painter.drawImage(dest, image)
        return target
    finally:
        painter.end()
