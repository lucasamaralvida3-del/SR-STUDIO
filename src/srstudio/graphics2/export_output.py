from __future__ import annotations

"""Production output pipeline for SR Graphics Engine 2.

This module deliberately sits *after* the renderer.  The renderer owns visual
semantics; this layer owns durable files, output dimensions, format policy,
page selection, batch naming and post-write validation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Literal
import os
import re
import uuid

from . import qt_renderer as _renderer
from .model import GraphicsDocument
from .qt_render_runtime import ensure_qt_gui_application

RasterFormat = Literal["png", "jpeg"]
ProgressCallback = Callable[[int, int, _renderer.RenderReport], None]

_FATAL_RENDER_WARNING_CODES = frozenset(
    {
        "IMAGE_SOURCE_EMPTY",
        "IMAGE_NOT_LOCAL",
        "IMAGE_DECODE_FAILED",
        "REMOTE_ASSET",
    }
)
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)
_INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ExportValidationError(RuntimeError):
    """Raised when an export cannot be proven valid enough to publish."""


@dataclass(slots=True)
class BatchRenderReport:
    format: str
    outputs: list[_renderer.RenderReport] = field(default_factory=list)

    @property
    def pages(self) -> int:
        return len(self.outputs)

    @property
    def warnings(self) -> list[_renderer.RenderWarning]:
        return [warning for report in self.outputs for warning in report.warnings]

    @property
    def ok(self) -> bool:
        return bool(self.outputs) and all(report.ok for report in self.outputs)


def export_png(
    document: GraphicsDocument,
    output: str | Path,
    *,
    page_index: int = 0,
    dpi: int = 300,
    target_width: int | None = None,
    target_height: int | None = None,
    transparent: bool = False,
    strict_assets: bool = True,
    overwrite: bool = True,
) -> _renderer.RenderReport:
    """Export one page as an atomically published PNG.

    ``target_width``/``target_height`` may be supplied independently.  When
    both are supplied they must preserve the page aspect ratio; the exporter
    never silently distorts a flyer to satisfy an incompatible size.
    """

    return _export_raster(
        document,
        output,
        page_index=page_index,
        raster_format="png",
        dpi=dpi,
        target_width=target_width,
        target_height=target_height,
        transparent=transparent,
        background=None,
        quality=100,
        strict_assets=strict_assets,
        overwrite=overwrite,
    )


def export_jpeg(
    document: GraphicsDocument,
    output: str | Path,
    *,
    page_index: int = 0,
    dpi: int = 300,
    target_width: int | None = None,
    target_height: int | None = None,
    quality: int = 92,
    background: str | None = None,
    strict_assets: bool = True,
    overwrite: bool = True,
) -> _renderer.RenderReport:
    """Export one page as JPEG, compositing transparency onto a background."""

    quality_value = int(quality)
    if not 1 <= quality_value <= 100:
        raise ValueError("Qualidade JPEG deve estar entre 1 e 100.")
    return _export_raster(
        document,
        output,
        page_index=page_index,
        raster_format="jpeg",
        dpi=dpi,
        target_width=target_width,
        target_height=target_height,
        transparent=False,
        background=background,
        quality=quality_value,
        strict_assets=strict_assets,
        overwrite=overwrite,
    )


def export_pdf(
    document: GraphicsDocument,
    output: str | Path,
    *,
    dpi: int = 600,
    page_indices: Iterable[int] | None = None,
    strict_assets: bool = True,
    overwrite: bool = True,
) -> _renderer.RenderReport:
    """Export a single- or multi-page PDF and publish it atomically.

    Rendering happens in a sibling temporary file.  The destination is only
    replaced after the complete PDF has a valid header/EOF marker and no fatal
    asset warnings.  A failure on an intermediate page therefore cannot leave
    a half-written destination masquerading as a successful export.
    """

    ensure_qt_gui_application()
    indices = _normalize_page_indices(document, page_indices)
    target = _prepare_target(output, ".pdf", overwrite=overwrite)
    temp = _temporary_sibling(target, ".pdf")
    try:
        report = _renderer.render_pdf(document, temp, dpi=_validated_dpi(dpi), page_indices=indices)
        _raise_for_fatal_warnings(report.warnings, strict_assets=strict_assets)
        _validate_pdf_file(temp)
        _publish(temp, target, overwrite=overwrite)
        return _renderer.RenderReport(target, "pdf", len(indices), warnings=list(report.warnings))
    finally:
        _remove_if_exists(temp)


def export_raster_batch(
    document: GraphicsDocument,
    output_dir: str | Path,
    *,
    raster_format: RasterFormat = "png",
    page_indices: Iterable[int] | None = None,
    base_name: str | None = None,
    dpi: int = 300,
    target_width: int | None = None,
    target_height: int | None = None,
    transparent: bool = False,
    jpeg_quality: int = 92,
    jpeg_background: str | None = None,
    strict_assets: bool = True,
    overwrite: bool = True,
    progress: ProgressCallback | None = None,
) -> BatchRenderReport:
    """Export selected pages sequentially without retaining a whole batch in RAM."""

    format_name = str(raster_format).lower()
    if format_name not in {"png", "jpeg"}:
        raise ValueError("Formato raster deve ser 'png' ou 'jpeg'.")
    indices = _normalize_page_indices(document, page_indices)
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise NotADirectoryError(f"Diretório de saída inválido: {directory}")

    stem = _batch_stem(base_name if base_name is not None else document.name)
    extension = ".png" if format_name == "png" else ".jpg"
    reports: list[_renderer.RenderReport] = []
    total = len(indices)
    for completed, page_index in enumerate(indices, start=1):
        target = directory / f"{stem}_p{page_index + 1:03d}{extension}"
        if format_name == "png":
            report = export_png(
                document,
                target,
                page_index=page_index,
                dpi=dpi,
                target_width=target_width,
                target_height=target_height,
                transparent=transparent,
                strict_assets=strict_assets,
                overwrite=overwrite,
            )
        else:
            report = export_jpeg(
                document,
                target,
                page_index=page_index,
                dpi=dpi,
                target_width=target_width,
                target_height=target_height,
                quality=jpeg_quality,
                background=jpeg_background,
                strict_assets=strict_assets,
                overwrite=overwrite,
            )
        reports.append(report)
        if progress is not None:
            progress(completed, total, report)
    return BatchRenderReport(format=format_name, outputs=reports)


def _export_raster(
    document: GraphicsDocument,
    output: str | Path,
    *,
    page_index: int,
    raster_format: RasterFormat,
    dpi: int,
    target_width: int | None,
    target_height: int | None,
    transparent: bool,
    background: str | None,
    quality: int,
    strict_assets: bool,
    overwrite: bool,
) -> _renderer.RenderReport:
    ensure_qt_gui_application()
    QtCore, QtGui = _renderer._qt()
    index = _validate_page_index(document, page_index)
    page = document.pages[index]
    dpi_value = _validated_dpi(dpi)
    width, height, scale = _raster_geometry(
        page.width,
        page.height,
        page.unit,
        dpi=dpi_value,
        target_width=target_width,
        target_height=target_height,
    )

    image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32_Premultiplied)
    if raster_format == "png" and transparent:
        image.fill(QtCore.Qt.transparent)
    else:
        color = QtGui.QColor(str(background or page.background or "#FFFFFF"))
        if not color.isValid():
            raise ValueError(f"Cor de fundo inválida para exportação: {background or page.background}")
        color.setAlpha(255)
        image.fill(color)
    dots_per_meter = max(1, round(dpi_value / 0.0254))
    image.setDotsPerMeterX(dots_per_meter)
    image.setDotsPerMeterY(dots_per_meter)

    font_report = _renderer.register_qt_document_fonts(document)
    warnings: list[_renderer.RenderWarning] = [
        _renderer.RenderWarning("FONT_REGISTRATION", item) for item in font_report.warnings
    ]
    painter = QtGui.QPainter(image)
    if not painter.isActive():
        raise RuntimeError("Qt não conseguiu iniciar o renderizador raster de exportação.")
    try:
        _renderer._configure_painter(painter, QtGui)
        painter.scale(scale, scale)
        # The base surface already encodes the requested page background policy.
        # Explicit BACKGROUND nodes still render normally as scene content.
        _renderer._render_page(
            painter,
            document,
            page,
            warnings,
            QtCore,
            QtGui,
            paint_background=False,
        )
    finally:
        painter.end()

    _raise_for_fatal_warnings(warnings, strict_assets=strict_assets)
    extension = ".png" if raster_format == "png" else ".jpg"
    target = _prepare_target(output, extension, jpeg_alias=raster_format == "jpeg", overwrite=overwrite)
    temp = _temporary_sibling(target, extension)
    try:
        qt_format = "PNG" if raster_format == "png" else "JPEG"
        qt_quality = 100 if raster_format == "png" else quality
        if not image.save(str(temp), qt_format, qt_quality):
            raise RuntimeError(f"Falha ao salvar {qt_format}: {target}")
        _validate_raster_file(temp, QtGui, width=width, height=height, expect_alpha=transparent)
        _publish(temp, target, overwrite=overwrite)
        return _renderer.RenderReport(target, raster_format, 1, width, height, warnings)
    finally:
        _remove_if_exists(temp)


def _normalize_page_indices(document: GraphicsDocument, page_indices: Iterable[int] | None) -> list[int]:
    if not document.pages:
        raise ValueError("Projeto sem páginas; não há conteúdo para exportar.")
    indices = list(range(len(document.pages))) if page_indices is None else [int(index) for index in page_indices]
    if not indices:
        raise ValueError("Nenhuma página selecionada para exportação.")
    if len(set(indices)) != len(indices):
        raise ValueError("Seleção de páginas contém páginas duplicadas.")
    for index in indices:
        _validate_page_index(document, index)
    return indices


def _validate_page_index(document: GraphicsDocument, page_index: int) -> int:
    if not document.pages:
        raise ValueError("Projeto sem páginas; não há conteúdo para exportar.")
    index = int(page_index)
    if index < 0 or index >= len(document.pages):
        raise IndexError(f"Página inexistente: {index + 1}.")
    return index


def _raster_geometry(page_width: float, page_height: float, unit, *, dpi: int, target_width: int | None, target_height: int | None) -> tuple[int, int, float]:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("Página com dimensões inválidas para exportação.")
    width_value = _positive_dimension(target_width, "largura")
    height_value = _positive_dimension(target_height, "altura")

    if width_value is not None and height_value is not None:
        sx = width_value / page_width
        sy = height_value / page_height
        if abs(sx - sy) > max(1e-6, min(sx, sy) * 0.002):
            raise ValueError(
                "Resolução solicitada altera a proporção da página; informe apenas uma dimensão "
                "ou use largura/altura compatíveis."
            )
        scale = (sx + sy) * 0.5
        return width_value, height_value, scale

    if width_value is not None:
        scale = width_value / page_width
        return width_value, max(1, round(page_height * scale)), scale
    if height_value is not None:
        scale = height_value / page_height
        return max(1, round(page_width * scale)), height_value, scale

    # Reuse the renderer's canonical unit-to-DPI conversion.
    class _PageProxy:
        width = page_width
        unit = unit

    scale = _renderer._raster_scale(_PageProxy(), dpi=dpi, target_width=None)
    return max(1, round(page_width * scale)), max(1, round(page_height * scale)), scale


def _positive_dimension(value: int | None, label: str) -> int | None:
    if value is None:
        return None
    result = int(value)
    if result <= 0:
        raise ValueError(f"{label.capitalize()} de saída deve ser maior que zero.")
    return result


def _validated_dpi(value: int) -> int:
    dpi = int(value)
    if dpi <= 0:
        raise ValueError("DPI de saída deve ser maior que zero.")
    if dpi > 2400:
        raise ValueError("DPI de saída acima de 2400 não é suportado por segurança de memória.")
    return dpi


def _prepare_target(output: str | Path, extension: str, *, jpeg_alias: bool = False, overwrite: bool) -> Path:
    target = Path(output).expanduser()
    accepted = {extension.lower()}
    if jpeg_alias:
        accepted.add(".jpeg")
    if target.suffix.lower() not in accepted:
        target = target.with_suffix(extension)
    _validate_filename(target.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.is_dir():
        raise NotADirectoryError(f"Diretório de saída inválido: {target.parent}")
    if target.exists() and target.is_dir():
        raise IsADirectoryError(f"Destino de exportação é um diretório: {target}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Arquivo já existe: {target}")
    return target


def _validate_filename(filename: str) -> None:
    name = str(filename or "")
    if not name or name in {".", ".."}:
        raise ValueError("Nome de arquivo de saída inválido.")
    if _INVALID_FILENAME_RE.search(name):
        raise ValueError(f"Nome de arquivo contém caractere inválido: {name}")
    stem = Path(name).stem.rstrip(" .").upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"Nome de arquivo reservado pelo Windows: {name}")
    if name.endswith((" ", ".")):
        raise ValueError(f"Nome de arquivo não pode terminar em espaço ou ponto: {name}")


def _batch_stem(value: str | None) -> str:
    raw = str(value or "encarte").strip()
    if not raw:
        raw = "encarte"
    cleaned = re.sub(r"\s+", "_", raw)
    cleaned = _INVALID_FILENAME_RE.sub("_", cleaned).strip(" ._") or "encarte"
    _validate_filename(f"{cleaned}.png")
    return cleaned


def _temporary_sibling(target: Path, extension: str) -> Path:
    return target.with_name(f".{target.stem}.{uuid.uuid4().hex}.tmp{extension}")


def _publish(temp: Path, target: Path, *, overwrite: bool) -> None:
    if target.exists() and not overwrite:
        raise FileExistsError(f"Arquivo já existe: {target}")
    try:
        os.replace(temp, target)
    except OSError as exc:
        raise OSError(f"Não foi possível publicar o arquivo exportado em '{target}': {exc}") from exc


def _validate_raster_file(path: Path, QtGui, *, width: int, height: int, expect_alpha: bool) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ExportValidationError(f"Arquivo raster vazio ou ausente: {path}")
    image = QtGui.QImage(str(path))
    if image.isNull():
        raise ExportValidationError(f"Arquivo raster gerado não pôde ser reaberto: {path}")
    if image.width() != width or image.height() != height:
        raise ExportValidationError(
            f"Dimensão raster divergente: esperado {width}x{height}, obtido {image.width()}x{image.height()}."
        )
    if expect_alpha and not image.hasAlphaChannel():
        raise ExportValidationError("PNG solicitado com transparência foi salvo sem canal alpha.")


def _validate_pdf_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 32:
        raise ExportValidationError(f"PDF vazio ou ausente: {path}")
    with path.open("rb") as handle:
        header = handle.read(8)
        handle.seek(max(0, path.stat().st_size - 4096))
        tail = handle.read()
    if not header.startswith(b"%PDF-"):
        raise ExportValidationError("Arquivo gerado não possui cabeçalho PDF válido.")
    if b"%%EOF" not in tail:
        raise ExportValidationError("PDF gerado não possui marcador final; possível arquivo truncado.")


def _raise_for_fatal_warnings(warnings: Iterable[_renderer.RenderWarning], *, strict_assets: bool) -> None:
    if not strict_assets:
        return
    fatal = [warning for warning in warnings if warning.code in _FATAL_RENDER_WARNING_CODES]
    if fatal:
        details = "; ".join(f"{warning.code}: {warning.message}" for warning in fatal[:5])
        if len(fatal) > 5:
            details += f"; +{len(fatal) - 5} erro(s)"
        raise ExportValidationError(f"Exportação interrompida por recurso obrigatório ausente: {details}")


def _remove_if_exists(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Cleanup must never mask the original export error.
        pass
