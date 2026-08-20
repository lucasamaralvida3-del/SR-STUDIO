from __future__ import annotations

"""PDF-specific paint-device adapter for production output.

The scene renderer remains the source of visual semantics. This adapter owns
only QPdfWriter page-device concerns: exact page size, zero output margins,
full-bleed page background, page transitions and final warning collection.
"""

from pathlib import Path
from typing import Iterable

from . import qt_renderer as renderer
from .model import GraphicsDocument
from .qt_render_runtime import ensure_qt_gui_application


def render_pdf(
    document: GraphicsDocument,
    output: str | Path,
    *,
    dpi: int = 600,
    page_indices: Iterable[int] | None = None,
) -> renderer.RenderReport:
    """Render selected pages to a PDF paint device with a true full-page surface."""

    ensure_qt_gui_application()
    QtCore, QtGui = renderer._qt()
    indices = list(range(len(document.pages))) if page_indices is None else [int(index) for index in page_indices]
    if not indices:
        raise ValueError("Nenhuma página selecionada para PDF.")
    if any(index < 0 or index >= len(document.pages) for index in indices):
        raise IndexError("Página inexistente na seleção de PDF.")

    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() != ".pdf":
        target = target.with_suffix(".pdf")

    font_report = renderer.register_qt_document_fonts(document)
    warnings: list[renderer.RenderWarning] = [
        renderer.RenderWarning("FONT_REGISTRATION", item) for item in font_report.warnings
    ]

    writer = QtGui.QPdfWriter(str(target))
    writer.setResolution(max(72, int(dpi)))
    writer.setCreator("SR Graphics Engine 2.0")
    writer.setTitle(document.name)
    _configure_pdf_page(writer, document.pages[indices[0]], QtCore, QtGui)

    painter = QtGui.QPainter(writer)
    if not painter.isActive():
        raise RuntimeError("Qt não conseguiu iniciar o renderizador PDF de produção.")
    try:
        renderer._configure_painter(painter, QtGui)
        for position, index in enumerate(indices):
            page = document.pages[index]
            if position:
                # Qt requires page layout changes immediately before newPage().
                _configure_pdf_page(writer, page, QtCore, QtGui)
                if not writer.newPage():
                    raise RuntimeError(f"Falha ao criar a página {position + 1} no PDF.")

            painter.save()
            try:
                logical_width = float(writer.width())
                logical_height = float(writer.height())
                if logical_width <= 0 or logical_height <= 0:
                    raise RuntimeError(
                        f"Área PDF inválida na página {position + 1}: {logical_width}x{logical_height}."
                    )

                # Paint the physical PDF paint rect before applying scene scale.
                # QPdfWriter rounds device dimensions independently at a given DPI;
                # relying on a scene-sized background can therefore leave a
                # sub-pixel white strip on one edge even when the MediaBox is exact.
                background = QtGui.QColor(str(page.background or "#FFFFFF"))
                if not background.isValid():
                    raise ValueError(f"Cor de fundo inválida na página {position + 1}: {page.background}")
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QBrush(background))
                painter.drawRect(QtCore.QRectF(0.0, 0.0, logical_width, logical_height))

                scale = min(
                    logical_width / max(float(page.width), 1e-6),
                    logical_height / max(float(page.height), 1e-6),
                )
                painter.scale(scale, scale)
                renderer._render_page(
                    painter,
                    document,
                    page,
                    warnings,
                    QtCore,
                    QtGui,
                    paint_background=False,
                )
            finally:
                painter.restore()
    finally:
        painter.end()

    return renderer.RenderReport(target, "pdf", len(indices), warnings=warnings)


def _configure_pdf_page(writer, page, QtCore, QtGui) -> None:
    page_size = renderer._qt_page_size(page, QtCore, QtGui)
    if not writer.setPageSize(page_size):
        raise RuntimeError(f"Qt recusou o tamanho físico da página '{page.name}'.")
    zero = QtCore.QMarginsF(0.0, 0.0, 0.0, 0.0)
    if not writer.setPageMargins(zero, QtGui.QPageLayout.Millimeter):
        raise RuntimeError(f"Qt recusou margens zero para a página '{page.name}'.")
