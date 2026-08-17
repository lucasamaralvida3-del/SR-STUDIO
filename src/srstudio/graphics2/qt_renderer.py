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
from .image_crop import crop_pixel_box
from .image_fill import drawingml_fill_destination, has_drawingml_fill_rect
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

        _draw_outer_shadow(painter, node, QtCore, QtGui)

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


def _draw_text(painter, node: GraphicsNode, QtCore, QtGui, *, color_override: str | None = None) -> None:
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
    painter.setPen(QtGui.QPen(QtGui.QColor(str(color_override or style.get("color") or "#111827"))))
    text = str(node.text or "")
    layout = _explicit_multiline_layout(text, rect, style, font, QtCore, QtGui)
    if layout is not None:
        painter.save()
        try:
            painter.setClipRect(rect)
            for line, x, baseline in layout:
                painter.drawText(QtCore.QPointF(x, baseline), line)
        finally:
            painter.restore()
        return
    painter.drawText(rect, flags, text)


def _explicit_multiline_layout(text: str, rect, style: dict, font, QtCore, QtGui):
    """Calcula linhas explícitas com o baseline spacing DrawingML exato.

    ``a:lnSpc/a:spcPts`` define a distância vertical entre baselines, não um
    fator genérico de fonte. O QPainter ``drawText(QRectF, ...)`` não expõe esse
    controle. Para textos que já possuem quebras explícitas e cabem horizontalmente
    na caixa, desenhamos cada linha no baseline calculado. Se uma linha precisar
    de word-wrap, retornamos ``None`` e mantemos a rota nativa do Qt para não
    inventar quebras diferentes do Office.
    """

    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in normalized:
        return None
    lines = normalized.split("\n")
    while len(lines) > 1 and lines[-1] == "":
        lines.pop()
    if len(lines) <= 1:
        return None

    metrics = QtGui.QFontMetricsF(font)
    line_advance = 0.0
    if style.get("line_spacing_px") not in (None, ""):
        try:
            line_advance = float(style.get("line_spacing_px") or 0.0)
        except (TypeError, ValueError):
            line_advance = 0.0
    elif style.get("line_spacing_percent") not in (None, ""):
        try:
            percent = float(style.get("line_spacing_percent") or 0.0)
        except (TypeError, ValueError):
            percent = 0.0
        if percent > 0:
            line_advance = metrics.height() * percent / 100.0
    if line_advance <= 0.0:
        return None

    widths = [float(metrics.horizontalAdvance(line)) for line in lines]
    if not bool(style.get("nowrap")) and any(width > rect.width() + 0.75 for width in widths):
        return None

    ascent = float(metrics.ascent())
    descent = float(metrics.descent())
    block_height = ascent + descent + line_advance * (len(lines) - 1)
    vertical = str(style.get("v_align") or style.get("vertical_align") or "center").lower()
    if vertical in {"top", "t"}:
        block_top = rect.top()
    elif vertical in {"bottom", "b"}:
        block_top = rect.bottom() - block_height
    else:
        block_top = rect.top() + (rect.height() - block_height) * 0.5
    first_baseline = block_top + ascent

    horizontal = str(style.get("align") or "center").lower()
    result: list[tuple[str, float, float]] = []
    for index, (line, width) in enumerate(zip(lines, widths)):
        if horizontal in {"left", "l"}:
            x = rect.left()
        elif horizontal in {"right", "r"}:
            x = rect.right() - width
        else:
            x = rect.left() + (rect.width() - width) * 0.5
        result.append((line, float(x), float(first_baseline + index * line_advance)))
    return result


def _draw_outer_shadow(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    shadow = node.style.get("shadow")
    if not isinstance(shadow, dict) or str(shadow.get("type") or "").lower() != "outer":
        return
    if node.kind not in {NodeKind.TEXT, NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.PATH}:
        return

    color = QtGui.QColor(str(shadow.get("color") or ""))
    if not color.isValid():
        return
    alpha = _clamp(float(shadow.get("alpha", 1.0) or 0.0), 0.0, 1.0)
    if alpha <= 0.0:
        return
    distance = max(0.0, float(shadow.get("distance", 0.0) or 0.0))
    blur = max(0.0, float(shadow.get("blur", 0.0) or 0.0))
    direction = float(shadow.get("direction", 0.0) or 0.0)
    rot_with_shape = bool(shadow.get("rot_with_shape", False))

    # O transform do node já está ativo no painter. DrawingML rotWithShape=0
    # mantém a direção da sombra no espaço da página, então compensamos a
    # rotação local antes de converter distância em deslocamento.
    if not rot_with_shape:
        direction -= float(node.transform.rotation or 0.0)
    radians = math.radians(direction)
    dx = math.cos(radians) * distance
    dy = math.sin(radians) * distance
    if not rot_with_shape:
        if abs(float(node.transform.scale_x or 1.0)) > 1e-9:
            dx /= float(node.transform.scale_x or 1.0)
        if abs(float(node.transform.scale_y or 1.0)) > 1e-9:
            dy /= float(node.transform.scale_y or 1.0)

    base_opacity = float(painter.opacity())
    for ox, oy, weight in _shadow_samples(blur):
        painter.save()
        try:
            painter.setOpacity(_clamp(base_opacity * alpha * weight, 0.0, 1.0))
            painter.translate(dx + ox, dy + oy)
            _draw_shadow_silhouette(painter, node, color, QtCore, QtGui)
        finally:
            painter.restore()


def _shadow_samples(blur: float) -> list[tuple[float, float, float]]:
    """Aproxima blur DrawingML com amostragem determinística do silhouette.

    QPainter puro não expõe blur de primitivas. Para manter a mesma rota PNG/PDF
    e evitar rasterizar o node inteiro, distribuímos 17 cópias leves em dois
    anéis. Blur zero continua sendo uma única cópia exata.
    """

    if blur <= 0.25:
        return [(0.0, 0.0, 1.0)]
    radius = min(24.0, max(0.75, blur * 0.70))
    samples: list[tuple[float, float, float]] = [(0.0, 0.0, 0.25)]
    for ring_radius, ring_weight in ((radius * 0.48, 0.075), (radius, 0.01875)):
        for index in range(8):
            angle = math.tau * index / 8.0
            samples.append((math.cos(angle) * ring_radius, math.sin(angle) * ring_radius, ring_weight))
    return samples


def _draw_shadow_silhouette(painter, node: GraphicsNode, color, QtCore, QtGui) -> None:
    if node.kind is NodeKind.TEXT:
        _draw_text(painter, node, QtCore, QtGui, color_override=color.name())
        return

    rect = QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height)
    painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
    painter.setBrush(QtGui.QBrush(color))
    if node.kind is NodeKind.ELLIPSE:
        painter.drawEllipse(rect)
        return
    if node.kind is NodeKind.PATH:
        custom = _custom_path(node.metadata.get("custom_path"), rect, QtGui)
        if custom is not None:
            painter.drawPath(custom)
        return
    if node.kind is NodeKind.RECT:
        custom = _custom_path(node.metadata.get("custom_path"), rect, QtGui)
        if custom is not None:
            painter.drawPath(custom)
            return
        radius = float(node.style.get("radius") or 0.0)
        if not radius and node.style.get("radius_ratio") not in (None, ""):
            radius = min(rect.width(), rect.height()) * max(0.0, float(node.style.get("radius_ratio") or 0.0))
        painter.drawRoundedRect(rect, radius, radius) if radius > 0 else painter.drawRect(rect)


def _should_fit_text(style: dict) -> bool:
    """Decide se o renderer pode reduzir o tamanho da fonte.

    ``nowrap`` desativa somente a quebra automática e nunca deve, sozinho,
    mudar a tipografia nem apagar quebras explícitas de parágrafo. Esse
    acoplamento fazia tokens como R$, 25, ,77 e KG receberem tamanhos diferentes
    no render de produção. ``overflow_only`` é reservado aos PriceBlocks: mantém
    o tamanho original e só permite redução caso o conteúdo realmente não caiba
    na caixa de origem.
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
    """Espelha o contrato QML Text.NoWrap/WordWrap no QPainter.

    DrawingML ``wrap=\"none\"`` significa *sem quebra automática*, não
    *forçar uma única linha*. Portanto não usamos ``Qt.TextSingleLine``: esse
    flag ignora caracteres de nova linha, enquanto o QML ``Text.NoWrap`` mantém
    quebras explícitas. Sem ``TextWordWrap`` o QPainter também preserva ``\n`` e
    deixa linhas longas excederem a largura, sendo recortadas pela caixa.
    """

    horizontal = str(style.get("align") or "center").lower()
    vertical = str(style.get("v_align") or style.get("vertical_align") or "center").lower()
    flags = QtCore.Qt.AlignLeft if horizontal in {"left", "l"} else QtCore.Qt.AlignRight if horizontal in {"right", "r"} else QtCore.Qt.AlignHCenter
    flags |= QtCore.Qt.AlignTop if vertical in {"top", "t"} else QtCore.Qt.AlignBottom if vertical in {"bottom", "b"} else QtCore.Qt.AlignVCenter
    if not bool(style.get("nowrap")):
        flags |= QtCore.Qt.TextWordWrap
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
    fill_rect = node.style.get("fill_rect")
    drawingml_stretch = has_drawingml_fill_rect(fill_rect)
    needs_clip = drawingml_stretch or clip_path is not None
    if needs_clip:
        painter.save()
        if drawingml_stretch:
            # fillRect pode ter offsets negativos e estender a fotografia para
            # fora da forma. O Office sempre recorta o preenchimento na forma.
            painter.setClipRect(target)
        if clip_path is not None:
            operation = QtCore.Qt.ClipOperation.IntersectClip if drawingml_stretch else QtCore.Qt.ClipOperation.ReplaceClip
            painter.setClipPath(clip_path, operation)
    try:
        if drawingml_stretch:
            destination = drawingml_fill_destination(target.width(), target.height(), fill_rect)
            dest = QtCore.QRectF(
                target.x() + destination.x,
                target.y() + destination.y,
                destination.width,
                destination.height,
            )
            painter.drawImage(dest, image)
            return

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
        if needs_clip:
            painter.restore()


def _crop_image(image, crop: dict, QtCore):
    x, y, width, height = crop_pixel_box(image.width(), image.height(), crop)
    if x == 0 and y == 0 and width == image.width() and height == image.height():
        return image
    return image.copy(QtCore.QRect(x, y, width, height))


def _draw_rect(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    style = node.style
    rect = QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height)
    painter.setPen(_pen(style, QtCore, QtGui))
    painter.setBrush(_brush(style, QtCore, QtGui, rect=rect))
    custom = _custom_path(node.metadata.get("custom_path"), rect, QtGui)
    if custom is not None:
        painter.drawPath(custom)
        return
    radius = float(style.get("radius") or 0.0)
    if not radius and style.get("radius_ratio") not in (None, ""):
        radius = min(rect.width(), rect.height()) * max(0.0, float(style.get("radius_ratio") or 0.0))
    painter.drawRoundedRect(rect, radius, radius) if radius > 0 else painter.drawRect(rect)


def _draw_ellipse(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    rect = QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height)
    painter.setPen(_pen(node.style, QtCore, QtGui))
    painter.setBrush(_brush(node.style, QtCore, QtGui, rect=rect))
    painter.drawEllipse(rect)


def _draw_line(painter, node: GraphicsNode, QtCore, QtGui) -> None:
    painter.setPen(_pen(node.style, QtCore, QtGui, default="#111827"))
    t = node.transform
    painter.drawLine(QtCore.QPointF(t.x, t.y), QtCore.QPointF(t.x + t.width, t.y + t.height))


def _draw_path(painter, page: GraphicsPage, node: GraphicsNode, warnings: list[RenderWarning], QtCore, QtGui) -> None:
    rect = QtCore.QRectF(node.transform.x, node.transform.y, node.transform.width, node.transform.height)
    custom = _custom_path(node.metadata.get("custom_path"), rect, QtGui)
    if custom is not None:
        painter.setPen(_pen(node.style, QtCore, QtGui))
        painter.setBrush(_brush(node.style, QtCore, QtGui, rect=rect))
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
    from PySide6.QtCore import QPointF
    return QPointF(x, y)


def _pen(style: dict, QtCore, QtGui, *, default: str = "transparent"):
    color = str(style.get("stroke") or style.get("outline") or default)
    width = max(0.0, float(style.get("stroke_width") or style.get("line_width") or 0.0))
    if color.lower() in {"", "none", "transparent"} or width <= 0:
        return QtGui.QPen(QtCore.Qt.NoPen)
    pen = QtGui.QPen(QtGui.QColor(color)); pen.setWidthF(width); pen.setJoinStyle(QtCore.Qt.RoundJoin); pen.setCapStyle(QtCore.Qt.RoundCap); return pen


def _brush(style: dict, QtCore, QtGui, *, rect=None):
    gradient = style.get("gradient")
    if rect is not None and isinstance(gradient, dict):
        brush = _linear_gradient_brush(gradient, rect, QtCore, QtGui)
        if brush is not None:
            return brush
    color = str(style.get("fill") or "transparent")
    if color.lower() in {"", "none", "transparent"}:
        return QtGui.QBrush(QtCore.Qt.NoBrush)
    return QtGui.QBrush(QtGui.QColor(color))


def _linear_gradient_brush(spec: dict, rect, QtCore, QtGui):
    if str(spec.get("type") or "").lower() != "linear":
        return None
    raw_stops = spec.get("stops")
    if not isinstance(raw_stops, list) or len(raw_stops) < 2:
        return None
    stops: list[tuple[float, object]] = []
    for item in raw_stops:
        if not isinstance(item, dict):
            continue
        color = QtGui.QColor(str(item.get("color") or ""))
        if not color.isValid():
            continue
        try:
            alpha = _clamp(float(item.get("alpha", 1.0)), 0.0, 1.0)
            position = _clamp(float(item.get("position", 0.0)), 0.0, 1.0)
        except (TypeError, ValueError):
            continue
        color.setAlphaF(alpha)
        stops.append((position, color))
    if len(stops) < 2:
        return None
    stops.sort(key=lambda item: item[0])

    angle = math.radians(float(spec.get("angle", 0.0) or 0.0))
    dx = math.cos(angle)
    dy = math.sin(angle)
    center = rect.center()
    half_span = abs(dx) * rect.width() * 0.5 + abs(dy) * rect.height() * 0.5
    half_span = max(0.5, half_span)
    start = QtCore.QPointF(center.x() - dx * half_span, center.y() - dy * half_span)
    end = QtCore.QPointF(center.x() + dx * half_span, center.y() + dy * half_span)
    gradient = QtGui.QLinearGradient(start, end)
    for position, color in stops:
        gradient.setColorAt(position, color)
    return QtGui.QBrush(gradient)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


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