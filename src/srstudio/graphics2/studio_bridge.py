from __future__ import annotations

"""Ponte de ativação controlada entre o shell Tk do Studio 5 e o Engine 2.

Tk e Qt possuem loops gráficos independentes. Para não misturar os dois loops
no mesmo processo, o modo experimental abre o Graphics Engine 2 em um processo
separado, passando um snapshot `.srscene` do projeto atual. A feature flag fica
desligada por padrão; este módulo apenas prepara a infraestrutura de migração.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import copy
import os
import shutil
import subprocess
import sys

from srstudio.core.models import StudioProject
from srstudio.settings.features import FeatureFlagStore

from .compat import from_studio_project
from .host_runtime import RUNTIME_MANIFEST_NAME, validate_runtime_host
from .legacy_merge import LEGACY_SOURCE_SNAPSHOT_KEY, LegacyMergeReport, merge_graphics_to_studio_non_conflicting
from .legacy_sync import LegacySyncReport, fingerprint_studio_project, sync_graphics_to_studio
from .package import load_package, save_package
from .quality import ProductionGateReport, inspect_production_gate

HOST_EXE_NAME = "SRGraphicsEngine2Host.exe"


@dataclass(slots=True, frozen=True)
class StudioBridgePreparation:
    package_path: Path
    gate: ProductionGateReport
    graphics_api: str
    reused_session: bool = False
    previous_package_path: Path | None = None


@dataclass(slots=True, frozen=True)
class StudioBridgeLaunchResult:
    ok: bool
    launched: bool
    message: str
    package_path: str = ""
    gate_score: int = 0
    graphics_api: str = ""
    pid: int = 0
    reused_session: bool = False


@dataclass(slots=True, frozen=True)
class StudioBridgeSyncResult:
    ok: bool
    message: str
    package_path: str = ""
    report: LegacySyncReport | LegacyMergeReport | None = None


def bridge_flags(data_dir: str | Path) -> tuple[bool, bool]:
    flags = FeatureFlagStore(Path(data_dir) / "feature-flags.json").load()
    return flags.enabled("graphics_engine_2"), flags.enabled("graphics_engine_2_gpu")


def prepare_studio_project(
    project: StudioProject,
    data_dir: str | Path,
    *,
    graphics_api: str = "auto",
) -> StudioBridgePreparation:
    """Prepara ou reutiliza a sessão persistente do projeto no Engine 2.

    Se o StudioProject ainda possui o mesmo fingerprint usado para criar a
    sessão anterior, o `.srscene` é reaberto em vez de ser regenerado. Isso
    preserva edições feitas somente no Engine 2. Se o projeto legado mudou, a
    sessão anterior é copiada para `.previous.srscene` antes da nova conversão.
    """

    runtime_dir = _bridge_runtime_dir(data_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    package_path = _bridge_package_path(project, data_dir)
    source_fingerprint = fingerprint_studio_project(project)
    previous_path: Path | None = None

    if package_path.is_file():
        try:
            existing = load_package(
                package_path,
                extract_assets_to=runtime_dir / "cache" / _safe_name(project.id or project.name),
            )
        except Exception:
            existing = None
        if existing is not None:
            existing_project_id = str(existing.metadata.get("legacy_project_id") or "")
            existing_fingerprint = str(existing.metadata.get("legacy_source_fingerprint") or "")
            if existing_project_id == str(project.id) and existing_fingerprint == source_fingerprint:
                gate = inspect_production_gate(existing, require_visual_fidelity=False)
                return StudioBridgePreparation(
                    package_path=package_path,
                    gate=gate,
                    graphics_api=graphics_api,
                    reused_session=True,
                )

        previous_path = package_path.with_name(package_path.stem + ".previous.srscene")
        try:
            shutil.copy2(package_path, previous_path)
        except OSError:
            previous_path = None

    document = from_studio_project(project)
    # A BASE e o fingerprint precisam existir dentro da primeira sessão. Sem
    # isso toda reabertura pareceria um projeto novo e o merge three-way não
    # teria um estado comum para separar mudanças Studio de mudanças G2.
    document.metadata["legacy_source_fingerprint"] = source_fingerprint
    document.metadata[LEGACY_SOURCE_SNAPSHOT_KEY] = copy.deepcopy(project.to_dict())
    gate = inspect_production_gate(document, require_visual_fidelity=False)
    # O snapshot é local e persistente por projeto. Assets que pertencem ao SR
    # Scene são empacotados; image_path legado continua apontando ao Banco SR.
    save_package(document, package_path, embed_local_assets=True)
    return StudioBridgePreparation(
        package_path=package_path,
        gate=gate,
        graphics_api=graphics_api,
        reused_session=False,
        previous_package_path=previous_path,
    )


def sync_saved_session_to_project(
    project: StudioProject,
    data_dir: str | Path,
    *,
    allow_conflict: bool = False,
    merge_non_conflicting: bool = False,
) -> StudioBridgeSyncResult:
    """Aplica ao Studio somente mudanças G2 representáveis pelo modelo 5.x.

    Por padrão o comportamento continua conservador: qualquer divergência entre
    Studio e a BASE bloqueia a escrita. Com ``merge_non_conflicting=True`` o
    bridge executa um three-way merge e aplica somente mudanças G2 que não
    colidem com alterações novas feitas no Studio.
    """

    package_path = _bridge_package_path(project, data_dir)
    if not package_path.is_file():
        return StudioBridgeSyncResult(
            ok=False,
            message="Nenhuma sessão salva do Graphics Engine 2 foi encontrada para este projeto.",
            package_path=str(package_path),
        )

    runtime_dir = _bridge_runtime_dir(data_dir)
    try:
        document = load_package(
            package_path,
            extract_assets_to=runtime_dir / "sync-cache" / _safe_name(project.id or project.name),
        )
    except Exception as exc:
        return StudioBridgeSyncResult(
            ok=False,
            message=f"A sessão do Graphics Engine 2 não pôde ser aberta: {exc}",
            package_path=str(package_path),
        )

    report: LegacySyncReport | LegacyMergeReport = sync_graphics_to_studio(
        document,
        project,
        allow_conflict=allow_conflict,
    )
    if not report.ok and report.conflict and merge_non_conflicting:
        report = merge_graphics_to_studio_non_conflicting(document, project)

    if not report.ok:
        detail = report.warnings[0] if report.warnings else "conflito desconhecido"
        return StudioBridgeSyncResult(
            ok=False,
            message=f"Sincronização bloqueada: {detail}",
            package_path=str(package_path),
            report=report,
        )

    if isinstance(report, LegacySyncReport):
        # O sync completo passa a considerar o resultado atual como nova BASE.
        document.metadata[LEGACY_SOURCE_SNAPSHOT_KEY] = copy.deepcopy(project.to_dict())
    try:
        # O sync/merge atualiza metadados de origem quando é seguro avançar a
        # BASE. Persistir o documento evita falso conflito na próxima abertura.
        save_package(document, package_path, embed_local_assets=True)
    except Exception as exc:
        return StudioBridgeSyncResult(
            ok=False,
            message=f"Alterações foram projetadas em memória, mas a sessão G2 não pôde ser atualizada: {exc}",
            package_path=str(package_path),
            report=report,
        )

    if isinstance(report, LegacyMergeReport):
        if report.conflicts:
            return StudioBridgeSyncResult(
                ok=True,
                message=(
                    f"Merge assistido aplicou {report.applied} alteração(ões) sem conflito · "
                    f"{report.unresolved_conflicts} conflito(s) permaneceram preservados no Engine 2."
                ),
                package_path=str(package_path),
                report=report,
            )
        return StudioBridgeSyncResult(
            ok=True,
            message=f"Merge assistido concluído · {report.applied} alteração(ões) aplicadas sem conflito.",
            package_path=str(package_path),
            report=report,
        )

    summary = (
        f"{report.products_updated} produto(s), {report.cards_updated} card(s) e "
        f"{report.pages_updated} página(s) atualizados"
    )
    if report.pages_reordered:
        summary += " · páginas reordenadas"
    if report.products_added:
        summary += f" · {report.products_added} produto(s) recuperados"
    return StudioBridgeSyncResult(
        ok=True,
        message=f"Alterações do Engine 2 aplicadas com segurança · {summary}.",
        package_path=str(package_path),
        report=report,
    )


def launch_studio_project_if_enabled(
    project: StudioProject,
    data_dir: str | Path,
    *,
    process_factory: Callable[..., Any] = subprocess.Popen,
) -> StudioBridgeLaunchResult:
    engine_enabled, gpu_enabled = bridge_flags(data_dir)
    if not engine_enabled:
        return StudioBridgeLaunchResult(
            ok=True,
            launched=False,
            message="SR Graphics Engine 2 permanece protegido pela feature flag.",
        )

    graphics_api = "auto" if gpu_enabled else "software"
    command = _host_command()
    if not command:
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message="Host separado do Graphics Engine 2 não está instalado, está corrompido ou é de outra versão.",
            graphics_api=graphics_api,
        )

    # Quando o host é um EXE separado ele leva o próprio runtime/Qt. Só o modo
    # de desenvolvimento `python -m ...` depende do PySide6 do processo atual.
    if _uses_current_python(command):
        from .qt_host import qt_quick_available

        if not qt_quick_available():
            return StudioBridgeLaunchResult(
                ok=False,
                launched=False,
                message="PySide6/Qt Quick não está disponível neste ambiente do SR Studio.",
                graphics_api=graphics_api,
            )

    try:
        prepared = prepare_studio_project(project, data_dir, graphics_api=graphics_api)
    except Exception as exc:
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"Falha ao preparar snapshot para o Engine 2: {exc}",
            graphics_api=graphics_api,
        )

    args = [*command, str(prepared.package_path), "--graphics-api", prepared.graphics_api]
    env = os.environ.copy()
    env["SR_GRAPHICS_ENGINE_2_BRIDGE"] = "1"
    env["SR_GRAPHICS_ENGINE_2_SOURCE_PROJECT"] = str(project.id or "")
    kwargs: dict[str, Any] = {
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True

    try:
        process = process_factory(args, **kwargs)
    except Exception as exc:
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"Não foi possível iniciar o Graphics Engine 2: {exc}",
            package_path=str(prepared.package_path),
            gate_score=prepared.gate.score,
            graphics_api=prepared.graphics_api,
            reused_session=prepared.reused_session,
        )

    gate_note = "gate aprovado" if prepared.gate.ready else f"gate {prepared.gate.score}/100 em validação"
    session_note = " · sessão G2 preservada" if prepared.reused_session else ""
    return StudioBridgeLaunchResult(
        ok=True,
        launched=True,
        message=f"Graphics Engine 2 aberto em processo isolado · {gate_note}{session_note}.",
        package_path=str(prepared.package_path),
        gate_score=prepared.gate.score,
        graphics_api=prepared.graphics_api,
        pid=int(getattr(process, "pid", 0) or 0),
        reused_session=prepared.reused_session,
    )


def discover_packaged_host() -> Path | None:
    """Localiza um host válido sem misturar runtime Qt ao processo Tk.

    Um caminho explícito por variável de ambiente é uma opção de desenvolvimento
    e pode apontar para um EXE sem manifesto. Candidatos instalados em locais
    canônicos só são aceitos quando possuem manifesto de runtime válido, SHA do
    executável correto e a mesma versão interna do Engine 2.
    """

    explicit = str(os.environ.get("SR_GRAPHICS_ENGINE_2_HOST") or "").strip()
    candidates: list[tuple[Path, bool]] = []
    if explicit:
        candidates.append((Path(explicit).expanduser(), False))

    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            (executable_dir / "Graphics2Host" / HOST_EXE_NAME, True),
            (executable_dir / HOST_EXE_NAME, True),
            (Path(__file__).resolve().parents[3] / "Graphics2Host" / HOST_EXE_NAME, True),
        ]
    )

    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        candidates.append(
            (Path(local_app_data) / "SRStudio" / "App" / "Graphics2Host" / HOST_EXE_NAME, True)
        )

    seen: set[str] = set()
    for candidate, require_manifest in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if not resolved.is_file():
            continue
        if _runtime_candidate_valid(resolved, require_manifest=require_manifest):
            return resolved
    return None


def _runtime_candidate_valid(executable: Path, *, require_manifest: bool) -> bool:
    manifest_path = executable.parent / RUNTIME_MANIFEST_NAME
    if not manifest_path.is_file():
        return not require_manifest
    try:
        # Import tardio evita ciclo durante a montagem de srstudio.graphics2.
        from . import ENGINE_VERSION

        report = validate_runtime_host(
            executable.parent,
            full=False,
            expected_engine_version=ENGINE_VERSION,
        )
    except Exception:
        return False
    return report.ok and report.executable == executable.resolve()


def _bridge_runtime_dir(data_dir: str | Path) -> Path:
    return Path(data_dir) / "graphics2-bridge"


def _bridge_package_path(project: StudioProject, data_dir: str | Path) -> Path:
    runtime_dir = _bridge_runtime_dir(data_dir)
    return runtime_dir / f"{_safe_name(project.id or project.name)}.srscene"


def _host_command() -> list[str]:
    packaged = discover_packaged_host()
    if packaged is not None:
        return [str(packaged)]
    if bool(getattr(sys, "frozen", False)):
        return []
    return [sys.executable, "-m", "srstudio.graphics2.entrypoint"]


def _uses_current_python(command: list[str]) -> bool:
    if len(command) < 3:
        return False
    try:
        current = Path(sys.executable).resolve()
        candidate = Path(command[0]).resolve()
    except OSError:
        return False
    return candidate == current and command[1:3] == ["-m", "srstudio.graphics2.entrypoint"]


def _safe_name(value: str) -> str:
    text = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value or "graphics2"))
    text = text.strip("-_")
    return text[:96] or "graphics2"