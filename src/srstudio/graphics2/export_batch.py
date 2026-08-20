from __future__ import annotations

"""Transactional raster batch publication for the G2 output pipeline."""

from pathlib import Path
from typing import Iterable
import os
import shutil
import uuid

from . import export_output as output
from .model import GraphicsDocument

# Alias separado para que testes/falhas de publicação final não contaminem a
# escrita atômica usada internamente pelos arquivos staged.
_atomic_replace = os.replace


def export_raster_batch(
    document: GraphicsDocument,
    output_dir: str | Path,
    *,
    raster_format: output.RasterFormat = "png",
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
    progress: output.ProgressCallback | None = None,
) -> output.BatchRenderReport:
    """Render a batch sequentially, then publish the complete set transactionally.

    Pages are rendered one at a time into a sibling staging directory, so the
    operation does not retain all QImages in memory. Final files are untouched
    until every page rendered and reopened successfully. During publication,
    existing targets are moved to backups; a later failure rolls already
    published pages back to their previous state.
    """

    format_name = str(raster_format).lower()
    if format_name not in {"png", "jpeg"}:
        raise ValueError("Formato raster deve ser 'png' ou 'jpeg'.")
    indices = output._normalize_page_indices(document, page_indices)
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise NotADirectoryError(f"Diretório de saída inválido: {directory}")

    stem = output._batch_stem(base_name if base_name is not None else document.name)
    extension = ".png" if format_name == "png" else ".jpg"
    targets = [directory / f"{stem}_p{page_index + 1:03d}{extension}" for page_index in indices]
    if not overwrite:
        existing = [target for target in targets if target.exists()]
        if existing:
            preview = ", ".join(target.name for target in existing[:3])
            if len(existing) > 3:
                preview += f", +{len(existing) - 3} arquivo(s)"
            raise FileExistsError(f"Batch não sobrescrito porque arquivo(s) já existem: {preview}")

    staging = directory / f".sr-g2-export-{uuid.uuid4().hex}.tmp"
    staging.mkdir(parents=False, exist_ok=False)
    staged: list[tuple[output._renderer.RenderReport, Path]] = []
    total = len(indices)
    try:
        for completed, (page_index, final_target) in enumerate(zip(indices, targets), start=1):
            staged_target = staging / final_target.name
            if format_name == "png":
                report = output.export_png(
                    document,
                    staged_target,
                    page_index=page_index,
                    dpi=dpi,
                    target_width=target_width,
                    target_height=target_height,
                    transparent=transparent,
                    strict_assets=strict_assets,
                    overwrite=True,
                )
            else:
                report = output.export_jpeg(
                    document,
                    staged_target,
                    page_index=page_index,
                    dpi=dpi,
                    target_width=target_width,
                    target_height=target_height,
                    quality=jpeg_quality,
                    background=jpeg_background,
                    strict_assets=strict_assets,
                    overwrite=True,
                )
            staged.append((report, final_target))
            if progress is not None:
                progress(completed, total, _logical_report(report, final_target))

        _publish_complete_batch(staged, staging=staging, overwrite=overwrite)
        reports: list[output._renderer.RenderReport] = []
        for report, final_target in staged:
            report.output = final_target
            reports.append(report)
        return output.BatchRenderReport(format=format_name, outputs=reports)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _logical_report(report, final_target: Path):
    return output._renderer.RenderReport(
        output=final_target,
        format=report.format,
        pages=report.pages,
        width=report.width,
        height=report.height,
        warnings=list(report.warnings),
    )


def _publish_complete_batch(staged: list[tuple[object, Path]], *, staging: Path, overwrite: bool) -> None:
    backup_dir = staging / "backups"
    backup_dir.mkdir(exist_ok=True)
    published: list[tuple[Path, Path | None]] = []

    try:
        for position, (report, target) in enumerate(staged):
            source = Path(report.output)
            if not source.is_file():
                raise output.ExportValidationError(f"Arquivo staged desapareceu antes da publicação: {source}")
            backup: Path | None = None
            if target.exists():
                if not overwrite:
                    raise FileExistsError(f"Arquivo já existe: {target}")
                if target.is_dir():
                    raise IsADirectoryError(f"Destino de batch é um diretório: {target}")
                backup = backup_dir / f"{position:04d}-{target.name}"
                try:
                    _atomic_replace(target, backup)
                except OSError as exc:
                    raise OSError(f"Não foi possível preparar sobrescrita de '{target}': {exc}") from exc
            try:
                _atomic_replace(source, target)
            except OSError as exc:
                if backup is not None and backup.exists():
                    try:
                        _atomic_replace(backup, target)
                    except OSError as restore_exc:
                        raise output.ExportValidationError(
                            f"Falha ao publicar '{target}' e ao restaurar o arquivo anterior: {restore_exc}"
                        ) from exc
                raise OSError(f"Não foi possível publicar página do batch em '{target}': {exc}") from exc
            published.append((target, backup))
    except Exception as exc:
        rollback_errors: list[str] = []
        for target, backup in reversed(published):
            try:
                target.unlink(missing_ok=True)
                if backup is not None and backup.exists():
                    _atomic_replace(backup, target)
            except OSError as restore_exc:
                rollback_errors.append(f"{target.name}: {restore_exc}")
        if rollback_errors:
            details = "; ".join(rollback_errors[:3])
            raise output.ExportValidationError(
                f"Batch falhou e o rollback ficou incompleto: {details}"
            ) from exc
        raise
