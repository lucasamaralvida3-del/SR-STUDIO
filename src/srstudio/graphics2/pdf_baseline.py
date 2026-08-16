from __future__ import annotations

"""Rasterização determinística de PDFs oficiais para Golden Masters visuais."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class PdfBaselinePage:
    index: int
    width: int
    height: int
    output: Path


def render_pdf_baselines(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    target_width: int = 2160,
    dpi: int = 144,
    prefix: str = "baseline",
) -> list[PdfBaselinePage]:
    """Renderiza todas as páginas do PDF para PNGs RGB.

    ``target_width`` tem prioridade porque evita diferenças dimensionais entre
    exportadores. Quando for zero, ``dpi`` define a escala (PDF usa pontos/72in).
    """

    try:
        import pypdfium2 as pdfium
    except Exception as exc:
        raise RuntimeError("pypdfium2 é necessário para gerar Golden Masters de PDF.") from exc

    source = Path(pdf_path)
    if not source.is_file():
        raise FileNotFoundError(f"PDF de referência não encontrado: {source}")
    if source.suffix.lower() != ".pdf":
        raise ValueError(f"Referência deve ser PDF: {source}")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    safe_prefix = _slug(prefix or source.stem)
    pages: list[PdfBaselinePage] = []

    with pdfium.PdfDocument(str(source)) as document:
        for index in range(len(document)):
            page = document[index]
            width_pt, _height_pt = page.get_size()
            if width_pt <= 0:
                raise ValueError(f"Página {index + 1} do PDF possui largura inválida.")
            scale = (int(target_width) / float(width_pt)) if int(target_width or 0) > 0 else max(1, int(dpi)) / 72.0
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().convert("RGB")
            target = destination / f"{safe_prefix}-page-{index + 1:03d}.png"
            image.save(target, "PNG", optimize=True)
            pages.append(PdfBaselinePage(index=index, width=image.width, height=image.height, output=target))
            image.close()
            close = getattr(bitmap, "close", None)
            if callable(close):
                close()
            page.close()
    return pages


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(value).strip())
    return cleaned.strip("-") or "baseline"
