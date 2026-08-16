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
import os
import subprocess
import sys

from srstudio.core.models import StudioProject
from srstudio.settings.features import FeatureFlagStore

from .compat import from_studio_project
from .host_runtime import RUNTIME_MANIFEST_NAME, validate_runtime_host
from .package import save_package
from .quality import ProductionGateReport, inspect_production_gate

HOST_EXE_NAME = "SRGraphicsEngine2Host.exe"


@dataclass(slots=True, frozen=True)
class StudioBridgePreparation:
    package_path: Path
    gate: ProductionGateReport
    graphics_api: str


@dataclass(slots=True, frozen=True)
class StudioBridgeLaunchResult:
    ok: bool
    launched: bool
    message: str
    package_path: str = ""
    gate_score: int = 0
    graphics_api: str = ""
    pid: int = 0


def bridge_flags(data_dir: str | Path) -> tuple[bool, bool]:
    flags = FeatureFlagStore(Path(data_dir) / "feature-flags.json").load()
    return flags.enabled("graphics_engine_2"), flags.enabled("graphics_engine_2_gpu")


def prepare_studio_project(
    project: StudioProject,
    data_dir: str | Path,
    *,
    graphics_api: str = "auto",
) -> StudioBridgePreparation:
    document = from_studio_project(project)
    gate = inspect_production_gate(document, require_visual_fidelity=False)
    runtime_dir = Path(data_dir) / "graphics2-bridge"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    package_path = runtime_dir / f"{_safe_name(project.id or project.name)}.srscene"
    # O snapshot é local e transitório. Assets que já pertencem ao SR Scene são
    # empacotados; image_path legado continua apontando ao Banco SR da máquina.
    save_package(document, package_path, embed_local_assets=True)
    return StudioBridgePreparation(package_path=package_path, gate=gate, graphics_api=graphics_api)


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
        )

    gate_note = "gate aprovado" if prepared.gate.ready else f"gate {prepared.gate.score}/100 em validação"
    return StudioBridgeLaunchResult(
        ok=True,
        launched=True,
        message=f"Graphics Engine 2 aberto em processo isolado · {gate_note}.",
        package_path=str(prepared.package_path),
        gate_score=prepared.gate.score,
        graphics_api=prepared.graphics_api,
        pid=int(getattr(process, "pid", 0) or 0),
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


def _host_command() -> list[str]:
    packaged = discover_packaged_host()
    if packaged is not None:
        return [str(packaged)]
    if bool(getattr(sys, "frozen", False)):
        return []
    return [sys.executable, "-m", "srstudio.graphics2.qt_host"]


def _uses_current_python(command: list[str]) -> bool:
    if len(command) < 3:
        return False
    try:
        current = Path(sys.executable).resolve()
        candidate = Path(command[0]).resolve()
    except OSError:
        return False
    return candidate == current and command[1:3] == ["-m", "srstudio.graphics2.qt_host"]


def _safe_name(value: str) -> str:
    text = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value or "graphics2"))
    text = text.strip("-_")
    return text[:96] or "graphics2"
