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
from .package import save_package
from .quality import ProductionGateReport, inspect_production_gate


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
            message="Host separado do Graphics Engine 2 ainda não foi empacotado neste instalador.",
            graphics_api=graphics_api,
        )

    if not os.environ.get("SR_GRAPHICS_ENGINE_2_HOST"):
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


def _host_command() -> list[str]:
    explicit = str(os.environ.get("SR_GRAPHICS_ENGINE_2_HOST") or "").strip()
    if explicit:
        return [explicit]
    if bool(getattr(sys, "frozen", False)):
        return []
    return [sys.executable, "-m", "srstudio.graphics2.qt_host"]


def _safe_name(value: str) -> str:
    text = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value or "graphics2"))
    text = text.strip("-_")
    return text[:96] or "graphics2"
