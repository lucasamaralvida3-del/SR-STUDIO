from __future__ import annotations

"""Bridge persistente para análise e resolução de conflitos Studio 5 ↔ G2.

Este módulo mantém a leitura/escrita do `.srscene` fora da UI e oferece uma
API segura para o shell Tk. A resolução é feita primeiro sobre cópias do
StudioProject e do GraphicsDocument; somente depois de persistir a sessão com
sucesso o projeto vivo é atualizado.
"""

from pathlib import Path
from typing import Mapping
import copy

from srstudio.core.models import StudioProject

from .legacy_merge import LegacyMergeReport, analyze_legacy_merge, resolve_legacy_merge_conflicts
from .model import GraphicsDocument
from .package import load_package, save_package
from .studio_bridge import StudioBridgeSyncResult, _bridge_package_path, _bridge_runtime_dir, _safe_name


def analyze_saved_session_merge(project: StudioProject, data_dir: str | Path) -> StudioBridgeSyncResult:
    package_path = _bridge_package_path(project, data_dir)
    document, error = _load_document(project, data_dir, package_path, "merge-analyze-cache")
    if document is None:
        return StudioBridgeSyncResult(
            ok=False,
            message=error or "A sessão do Graphics Engine 2 não pôde ser aberta.",
            package_path=str(package_path),
        )

    report = analyze_legacy_merge(document, project)
    if not report.ok:
        detail = report.warnings[0] if report.warnings else "não foi possível analisar a sessão"
        return StudioBridgeSyncResult(
            ok=False,
            message=f"Análise de conflitos bloqueada: {detail}",
            package_path=str(package_path),
            report=report,
        )

    if report.conflict:
        message = f"{report.unresolved_conflicts} conflito(s) precisam de decisão por campo."
    else:
        message = "Studio e Graphics Engine 2 estão compatíveis; não há conflitos pendentes."
    return StudioBridgeSyncResult(
        ok=True,
        message=message,
        package_path=str(package_path),
        report=report,
    )


def resolve_saved_session_merge(
    project: StudioProject,
    data_dir: str | Path,
    resolutions: Mapping[str, str],
    *,
    apply_non_conflicting: bool = True,
) -> StudioBridgeSyncResult:
    package_path = _bridge_package_path(project, data_dir)
    document, error = _load_document(project, data_dir, package_path, "merge-resolve-cache")
    if document is None:
        return StudioBridgeSyncResult(
            ok=False,
            message=error or "A sessão do Graphics Engine 2 não pôde ser aberta.",
            package_path=str(package_path),
        )

    working_project = copy.deepcopy(project)
    working_document = GraphicsDocument.from_dict(document.to_dict())
    report = resolve_legacy_merge_conflicts(
        working_document,
        working_project,
        dict(resolutions or {}),
        apply_non_conflicting=apply_non_conflicting,
    )
    if not report.ok:
        detail = report.warnings[0] if report.warnings else "não foi possível resolver os conflitos"
        return StudioBridgeSyncResult(
            ok=False,
            message=f"Resolução bloqueada: {detail}",
            package_path=str(package_path),
            report=report,
        )

    try:
        save_package(working_document, package_path, embed_local_assets=True)
    except Exception as exc:
        return StudioBridgeSyncResult(
            ok=False,
            message=f"As decisões não foram aplicadas porque a sessão G2 não pôde ser salva: {exc}",
            package_path=str(package_path),
            report=report,
        )

    _replace_project(project, working_project)
    if report.conflict:
        message = (
            f"{report.resolved} conflito(s) resolvido(s); "
            f"{report.unresolved_conflicts} ainda aguardam decisão."
        )
    else:
        message = (
            f"Conflitos resolvidos com segurança · {report.resolved} decisão(ões) explícita(s) · "
            f"{report.applied} alteração(ões) aplicadas."
        )
    return StudioBridgeSyncResult(
        ok=True,
        message=message,
        package_path=str(package_path),
        report=report,
    )


def _load_document(
    project: StudioProject,
    data_dir: str | Path,
    package_path: Path,
    cache_name: str,
) -> tuple[GraphicsDocument | None, str]:
    if not package_path.is_file():
        return None, "Nenhuma sessão salva do Graphics Engine 2 foi encontrada para este projeto."
    runtime_dir = _bridge_runtime_dir(data_dir)
    try:
        document = load_package(
            package_path,
            extract_assets_to=runtime_dir / cache_name / _safe_name(project.id or project.name),
        )
    except Exception as exc:
        return None, f"A sessão do Graphics Engine 2 não pôde ser aberta: {exc}"
    return document, ""


def _replace_project(target: StudioProject, source: StudioProject) -> None:
    target.schema_version = source.schema_version
    target.id = source.id
    target.name = source.name
    target.campaign = source.campaign
    target.products = source.products
    target.pages = source.pages
    target.settings = source.settings
