from __future__ import annotations

"""Renderizador de produção do SR Graphics Engine 2 usando o mesmo stack Qt.

O editor interativo usa Qt Quick; este módulo usa QPainter/QPdfWriter para
exportar PNG/PDF sem depender do tamanho da janela ou do zoom do usuário.
A geometria persistida em SR Scene continua sendo a única fonte de verdade.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import math

from .fonts import register_qt_document_fonts
from .model import CoordinateUnit, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect
from .preflight import run_preflight


@dataclass(slots=True)
class RenderWarning:
    code: str
    message: str
    page_id: str = ""
    node_id: str = ""


@dataclass(slots=True)
class RenderReport:
    output: Path
    format: str
    pages: int
    width: int = 0
    height: int = 0
    warnings: list[RenderWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.output.is_file() and self.output.stat().st_size > 0


def qt_renderer_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except Exception:
        return False
    return True


def render_png(
    document: GraphicsDocument,
    output: str | Path,
    *,
    page_index: int = 0,
    dpi: int = 300,
    target_width: int | None = None,
    transparent: bool = False,
) -> RenderReport:
    QtCore, QtGui = _qt()
    if not 0 <= page_index < len(document.pages):
        raise IndexError("Página inexistente.")
    font_report = register_qt_document_fonts(document)
    page = document.pages[page_index]
    scale = _raster_scale(page, dpi=dpi, target_width=target_width)
    width = max(1, round(page.width * scale))
    height = max(1, round(page.height * scale))
    image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent if transparent else QtGui.QColor(page.background))
    painter = QtGui.QPainter(image)
    if not painter.isActive():
        raise RuntimeError("Qt não conseguiu iniciar o renderizador raster.")
    warnings: list[RenderWarning] = [RenderWarning("FONT_REGISTRATION", item) for item in font_report.warnings]
    try:
        _configure_painter(painter, QtGui)
        painter.scale(scale, scale)
        _render_page(painter, document, page, warnings, QtCore, QtGui, paint_background=transparent)
    finally:
        painter.end()
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() != ".png":
        target = target.with_suffix(".png")
    if not image.save(str(target), "PNG", 100):
        raise RuntimeError(f"Falha ao salvar PNG: {target}")
    return RenderReport(target, "png", 1, width, height, warnings)


def render_pdf(
    document: GraphicsDocument,
    output: str | Path,
    *,
    dpi: int = 600,
    page_indices: Iterable[int] | None = None,
) -> RenderReport:
    QtCore, QtGui = _qt()
    indices = list(range(len(document.pages))) if page_indices is None else [int(i) for i in page_indices]
    if not indices:
        raise ValueError("Nenhuma página selecionada para PDF.")
    if any(index < 0 or index >= len(document.pages) for index in indices):
        raise IndexError("Página inexistente na seleção de PDF.")
    font_report = register_qt_document_fonts(document)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() != ".pdf":
        target = target.with_suffix(".pdf")
    writer = QtGui.QPdfWriter(str(target))
    writer.setResolution(max(72, int(dpi)))
    writer.setCreator("SR Graphics Engine 2.0")
    writer.setTitle(document.name)
    first = document.pages[indices[0]]
    writer.setPageSize(_qt_page_size(first, QtCore, QtGui))
    painter = QtGui.QPainter(writer)
    if not painter.isActive():
        raise RuntimeError("Qt não conseguiu iniciar o renderizador PDF.")
    warnings: list[RenderWarning] = [RenderWarning("FONT_REGISTRATION", item) for item in font_report.warnings]
    try:
        _configure_painter(painter, QtGui)
        for position, index in enumerate(indices):
            page = document.pages[index]
            if position:
                writer.setPageSize(_qt_page_size(page, QtCore, QtGui))
                if not writer.newPage():
                    raise RuntimeError("Falha ao criar nova página no PDF.")
            painter.save()
            try:
                logical_width_px = writer.width()
                logical_height_px = writer.height()
                scale = min(logical_width_px / max(page.width, 1e-6), logical_height_px / max(page.height, 1e-6))
                painter.scale(scale, scale)
                _render_page(painter, document, page, warnings, QtCore, QtGui, paint_background=True)
            finally:
                painter.restore()
    finally:
        painter.end()
    return RenderReport(target, "pdf", len(indices), warnings=warnings)


def validate_renderability(document: GraphicsDocument) -> list[RenderWarning]:
    warnings = [RenderWarning(issue.code, issue.message, issue.page_id, issue.node_id) for issue in run_preflight(document)]
    for page in document.pages:
        for node in page.nodes.values():
            if node.kind is NodeKind.PATH and not node.metadata.get("svg_path") and not node.metadata.get("custom_path"):
                warnings.append(RenderWarning("PATH_UNSUPPORTED", "Path sem geometria vetorial; será ignorado até a conversão de geometria.", page.id, node.id))
            if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND} and _image_source(document, node):
                source = _image_source(document, node)
                if not _source_is_local(source):
                    warnings.append(RenderWarning("REMOTE_ASSET", "Asset remoto deve ser materializado antes da exportação de produção.", page.id, node.id))
    return warnings


def _qt():
    try:
        from PySide6 import QtCore, QtGui
    except Exception as exc:
        raise RuntimeError("Renderização Qt requer o extra 'graphics2' (PySide6).") from exc
    return QtCore, QtGui


def _configure_painter(painter, QtGui) -> None:
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
    painter.setRenderHint(QtGui.QPainter.LosslessImageRendering, True)


def _render_page(painter, document: GraphicsDocument, page: GraphicsPage, warnings: list[RenderWarning], QtCore, QtGui, *, paint_background: bool) -> None:
    if paint_background:
        painter.save()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(page.background)))
        painter.drawRect(QtCore.QRectF(0, 0, page.width, page.height))
        painter.restore()
    selected_roots = [node for node in page.ordered_nodes() if node.visible and not _has_hidden_ancestor(page, node)]
    for node in selected_roots:
        if node.kind is NodeKind.GROUP:
            continue
        _render_node(painter, document, page, node, warnings, QtCore, QtGui)


def _render_node(painter, document: GraphicsDocument, page: GraphicsPage, node: GraphicsNode, warnings: list[RenderWarning], QtCore, QtGui) -> None:
    t = node.transform
    if t.width <= 0 and t.height <= 0 and node.kind is not NodeKind.LINE:
        return
    painter.save()
    try:
        painter.setOpacity(max(0.0, min(1.0, float(node.opacity))))
        cx = t.x + t.width * t.pivot_x
        cy = t.y + t.height * t.pivot_y
        if t.rotation:
            painter.translate(cx, cy)
            painter.rotate(float(t.rotation))
            painter.translate(-cx, -cy)
        if t.scale_x != 1.0 or t.scale_y != 1.0:
            painter.translate(cx, cy)
            painter.scale(float(t.scale_x), float(t.scale_y))
            painter.translate(-cx, -cy)
        if node.kind is NodeKind.TEXT:
            _draw_text(painter, node, QtCore, QtGui)
        elif node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
            _draw_image(painter, document, page, node, warnings, QtCore, QtGui)
        elif node.kind is NodeKind.RECT:
            _draw_rect(painter, node, QtCore, QtGui)
        elif node.kind is NodeKind.ELLIPSE:
            _draw_ellipse(painter, node, QtCore, QtGui)
        elif node.kind is NodeKind.LINE:
            _draw_line(painter, node, QtCore, QtGui)
        elif node.kind is NodeKind.PATH:
            _draw_path(painter, page, node, warnings, QtCore, QtGui)
    finally:
        painter.restore()


def _draw_text(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    t = node.transform
    style = node.style
    insets = dict(style.get("text_insets") or {})
    left = max(0.0, float(insets.get("left", 0.0) or 0.0))
    top = max(0.0, float(insets.get("top", 0.0) or 0.0))
    right = max(0.0, float(insets.get("right", 0.0) or 0.0))
    bottom = max(0.0, float(insets.get("bottom", 0.0) or 0.0))
    rect = QtCore.QRectF(
        t.x + left,
        t.y + top,
        max(0.1, t.width - left - right),
        max(0.1, t.height - top - bottom),
    )
    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
    base_size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    logical_px = base_size * (96.0 / 72.0) if unit in {"pt", "point", "points"} else base_size
    font = QtGui.QFont(family)
    font.setPixelSize(max(1, round(logical_px)))
    font.setBold(float(style.get("font_weight") or 400) >= 700)
    font.setItalic(bool(style.get("italic")))
    if style.get("letter_spacing") not in (None, ""):
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0))
    flags = _text_flags(style, QtCore)
    if _should_fit_text(style):
        font = _fit_font(
            font,
            str(node.text or ""),
            rect,
            flags,
            QtCore,
            QtGui,
            min_px=max(3, round(float(style.get("min_font_size") or 4))),
        )
    painter.setFont(font)
    painter.setPen(QtGui.QPen(QtGui.QColor(str(style.get("color") or "#111827"))))
    painter.drawText(rect, flags, str(node.text or ""))


def _should_fit_text(style: dict) -> bool:
    """Decide se o renderer pode reduzir o tamanho da fonte.

    ``nowrap`` significa somente linha única e nunca deve, sozinho, mudar a
    tipografia. Esse acoplamento fazia tokens como R$, 25, ,77 e KG receberem
    tamanhos diferentes no render de produção. ``overflow_only`` é reservado
    aos PriceBlocks: mantém o tamanho original e só permite redução caso o
    conteúdo realmente não caiba na caixa de origem.
    """

    if bool(style.get("fit_inside_box")):
        return True
    return str(style.get("semantic_fit_policy") or "").lower() == "overflow_only"


def _fit_font(font, text: str, rect, flags, QtCore, QtGui, *, min_px: int) -> object:
    if not text or rect.width() <= 0 or rect.height() <= 0:
        return font
    hi = max(min_px, font.pixelSize())
    lo = min(min_px, hi)
    best = lo
    for _ in range(16):
        mid = (lo + hi) / 2.0
        trial = QtGui.QFont(font)
        trial.setPixelSize(max(1, round(mid)))
        metrics = QtGui.QFontMetricsF(trial)
        measured = metrics.boundingRect(QtCore.QRectF(0, 0, rect.width(), rect.height()), flags, text)
        if measured.width() <= rect.width() + 0.75 and measured.height() <= rect.height() + 0.75:
            best = mid
            lo = mid
        else:
            hi = mid
    result = QtGui.QFont(font)
    result.setPixelSize(max(1, round(best)))
    return result


def _text_flags(style: dict, QtCore) -> object:
    horizontal = str(style.get("align") or "center").lower()
    vertical = str(style.get("v_align") or style.get("vertical_align") or "center").lower()
    flags = QtCore.Qt.AlignLeft if horizontal in {"left", "l"} else QtCore.Qt.AlignRight if horizontal in {"right", "r"} else QtCore.Qt.AlignHCenter
    flags |= QtCore.Qt.AlignTop if vertical in {"top", "t"} else QtCore.Qt.AlignBottom if vertical in {"bottom", "b"} else QtCore.Qt.AlignVCenter
    flags |= QtCore.Qt.TextSingleLine if bool(style.get("nowrap")) else QtCore.Qt.TextWordWrap
    return flags


def _draw_image(painter, document: GraphicsDocument, page: GraphicsPage, node: GraphicsNode, warnings: list[RenderWarning], QtCore, QtGui) -> None:
    source = _image_source(document, node)
    if not source:
        warnings.append(RenderWarning("IMAGE_SOURCE_EMPTY", "Imagem sem origem local.", page.id, node.id))
        return
    local = _local_path(source, QtCore)
    if not local or not Path(local).is_file():
        warnings.append(RenderWarning("IMAGE_NOT_LOCAL", f"Imagem indisponível para exportação: {source}", page.id, node.id))
        return
    image = QtGui.QImage(str(local))
    if image.isNull():
        warnings.append(RenderWarning("IMAGE_DECODE_FAILED", f"Qt não conseguiu abrir a imagem: {local}", page.id, node.id))
        return
    crop = dict(node.style.get("crop") or {})
    if crop:
        image = _crop_image(image, crop, QtCore)
    if bool(node.style.get("flip_x")) or bool(node.style.get("flip_y")):
        image = image.mirrored(bool(node.style.get("flip_x")), bool(node.style.get("flip_y")))
    target = QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height)
    clip_path = _custom_path(node.metadata.get("clip_path"), target, QtGui)
    if clip_path is not None:
        painter.save()
        painter.setClipPath(clip_path)
    try:
        fit = str(node.style.get("fit") or "contain").lower()
        focus_x = min(1.0, max(0.0, float(node.style.get("focus_x", 0.5) or 0.5)))
        focus_y = min(1.0, max(0.0, float(node.style.get("focus_y", 0.5) or 0.5)))
        zoom = max(0.05, float(node.style.get("zoom", 1.0) or 1.0))
        if fit == "fill":
            painter.drawImage(target, image)
            return
        iw, ih = float(image.width()), float(image.height())
        tw, th = max(0.1, target.width()), max(0.1, target.height())
        if fit == "cover" or zoom > 1.0001:
            scale = max(tw / iw, th / ih) * zoom
            source_w = min(iw, tw / scale)
            source_h = min(ih, th / scale)
            source_x = (iw - source_w) * focus_x
            source_y = (ih - source_h) * focus_y
            source_rect = QtCore.QRectF(source_x, source_y, source_w, source_h)
            painter.drawImage(target, image, source_rect)
            return
        scale = min(tw / iw, th / ih)
        dw, dh = iw * scale, ih * scale
        dest = QtCore.QRectF(target.x() + (tw - dw) * focus_x, target.y() + (th - dh) * focus_y, dw, dh)
        painter.drawImage(dest, image)
    finally:
        if clip_path is not None:
            painter.restore()


def _crop_image(image, crop: dict, QtCore):
    try:
        left = min(0.98, max(0.0, float(crop.get("l", crop.get("left", 0.0)) or 0.0)))
        top = min(0.98, max(0.0, float(crop.get("t", crop.get("top", 0.0)) or 0.0)))
        right = min(0.98, max(0.0, float(crop.get("r", crop.get("right", 0.0)) or 0.0)))
        bottom = min(0.98, max(0.0, float(crop.get("b", crop.get("bottom", 0.0)) or 0.0)))
    except (TypeError, ValueError):
        return image
    x = round(image.width() * left)
    y = round(image.height() * top)
    width = round(image.width() * max(0.001, 1.0 - left - right))
    height = round(image.height() * max(0.001, 1.0 - top - bottom))
    return image.copy(QtCore.QRect(x, y, max(1, width), max(1, height)))


def _draw_rect(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    style = node.style
    painter.setPen(_pen(style, QtCore, QtGui))
    painter.setBrush(_brush(style, QtCore, QtGui))
    rect = QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height)
    custom = _custom_path(node.metadata.get("custom_path"), rect, QtGui)
    if custom is not None:
        painter.drawPath(custom)
        return
    radius = float(style.get("radius") or 0.0)
    if not radius and style.get("radius_ratio") not in (None, ""):
        radius = min(rect.width(), rect.height()) * max(0.0, float(style.get("radius_ratio") or 0.0))
    painter.drawRoundedRect(rect, radius, radius) if radius > 0 else painter.drawRect(rect)


def _draw_ellipse(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    painter.setPen(_pen(node.style, QtCore, QtGui)); painter.setBrush(_brush(node.style, QtCore, QtGui))
    painter.drawEllipse(QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height))


def _draw_line(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    painter.setPen(_pen(node.style, QtCore, QtGui, default="#111827"))
    t = node.transform
    painter.drawLine(QtCore.QPointF(t.x, t.y), QtCore.QPointF(t.x + t.width, t.y + t.height))


def _draw_path(painter, page: GraphicsPage, node: GraphicsNode, warnings: list[RenderWarning], QtCore, QtGui) -> None:
    rect = QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height)
    custom = _custom_path(node.metadata.get("custom_path"), rect, QtGui)
    if custom is not None:
        painter.setPen(_pen(node.style, QtCore, QtGui))
        painter.setBrush(_brush(node.style, QtCore, QtGui))
        painter.drawPath(custom)
        return
    path_text = str(node.metadata.get("svg_path") or "").strip()
    if not path_text:
        warnings.append(RenderWarning("PATH_UNSUPPORTED", "Path sem geometria vetorial; elemento ignorado.", page.id, node.id))
        return
    warnings.append(RenderWarning("PATH_DEFERRED", "Path SVG preservado no SR Scene; parser SVG dedicado ainda não aplicado neste render.", page.id, node.id))


def _custom_path(spec: object, target, QtGui):
    if not isinstance(spec, dict):
        return None
    paths = list(spec.get("paths") or [])
    if not paths:
        return None
    result = QtGui.QPainterPath()
    for item in paths:
        if not isinstance(item, dict):
            continue
        width = max(1e-9, float(item.get("width") or spec.get("width") or 0.0))
        height = max(1e-9, float(item.get("height") or spec.get("height") or 0.0))
        sx = target.width() / width
        sy = target.height() / height

        def point(raw):
            return QtCorePoint(target.x() + float(raw[0]) * sx, target.y() + float(raw[1]) * sy, QtGui)

        for command in item.get("commands") or []:
            if not isinstance(command, dict):
                continue
            op = str(command.get("op") or "")
            points = list(command.get("points") or [])
            if op == "M" and points:
                p = point(points[0]); result.moveTo(p)
            elif op == "L" and points:
                p = point(points[0]); result.lineTo(p)
            elif op == "C" and len(points) >= 3:
                a, b, c = point(points[0]), point(points[1]), point(points[2]); result.cubicTo(a, b, c)
            elif op == "Q" and len(points) >= 2:
                a, b = point(points[0]), point(points[1]); result.quadTo(a, b)
            elif op == "Z":
                result.closeSubpath()
    return result if not result.isEmpty() else None


def QtCorePoint(x: float, y: float, QtGui):
    # QPainterPath aceita QPointF; importar QtCore aqui criaria dependência global.
    from PySide6.QtCore import QPointF
    return QPointF(x, y)


def _pen(style: dict, QtCore, QtGui, *, default: str = "transparent"):
    color = str(style.get("stroke") or style.get("outline") or default)
    width = max(0.0, float(style.get("stroke_width") or style.get("line_width") or 0.0))
    if color.lower() in {"", "none", "transparent"} or width <= 0:
        return QtGui.QPen(QtCore.Qt.NoPen)
    pen = QtGui.QPen(QtGui.QColor(color)); pen.setWidthF(width); pen.setJoinStyle(QtCore.Qt.RoundJoin); pen.setCapStyle(QtCore.Qt.RoundCap); return pen


def _brush(style: dict, QtCore, QtGui):
    color = str(style.get("fill") or "transparent")
    if color.lower() in {"", "none", "transparent"}:
        return QtGui.QBrush(QtCore.Qt.NoBrush)
    return QtGui.QBrush(QtGui.QColor(color))


def _image_source(document: GraphicsDocument, node: GraphicsNode) -> str:
    if node.asset_id and node.asset_id in document.assets:
        source = str(document.assets[node.asset_id].source or "")
        if source:
            return source
    return str(node.metadata.get("bound_image_source") or node.metadata.get("source_url") or "")


def _source_is_local(source: str) -> bool:
    text = str(source or "")
    return text.startswith("file:") or Path(text).is_absolute()


def _local_path(source: str, QtCore) -> str:
    text = str(source or "").strip()
    if not text:
        return ""
    if text.startswith("file:"):
        return str(QtCore.QUrl(text).toLocalFile())
    return text if Path(text).is_absolute() else ""


def _has_hidden_ancestor(page: GraphicsPage, node: GraphicsNode) -> bool:
    parent_id = node.parent_id
    seen: set[str] = set()
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = page.node(parent_id)
        if parent is None:
            return False
        if not parent.visible:
            return True
        parent_id = parent.parent_id
    return False


def _raster_scale(page: GraphicsPage, *, dpi: int, target_width: int | None) -> float:
    if target_width:
        return max(0.01, int(target_width) / max(page.width, 1e-6))
    if page.unit is CoordinateUnit.MILLIMETER:
        return max(0.01, int(dpi) / 25.4)
    if page.unit is CoordinateUnit.POINT:
        return max(0.01, int(dpi) / 72.0)
    return max(0.01, int(dpi) / 96.0)


def _qt_page_size(page: GraphicsPage, QtCore, QtGui):
    width_mm, height_mm = _page_size_mm(page)
    return QtGui.QPageSize(QtCore.QSizeF(width_mm, height_mm), QtGui.QPageSize.Millimeter, page.name)


def _page_size_mm(page: GraphicsPage) -> tuple[float, float]:
    if page.unit is CoordinateUnit.MILLIMETER:
        return page.width, page.height
    if page.unit is CoordinateUnit.POINT:
        return page.width * 25.4 / 72.0, page.height * 25.4 / 72.0
    return page.width * 25.4 / 96.0, page.height * 25.4 / 96.0
