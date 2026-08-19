from __future__ import annotations

"""Primary SR Studio -> Graphics Engine 2 activation bridge.

This module promotes the already-certified separated Qt host to the normal
Encartes Studio flow without changing the import pipeline. PPTX/Canva exports
are passed to the host as the original source path, so ``qt_host`` continues to
own ``GraphicsImportService -> UnifiedImportPipeline -> SR Scene 2``.

The legacy ``studio_bridge`` remains responsible for runtime discovery,
persistent ``.srscene`` snapshots and compatibility sync. No Qt objects are
created inside the Tk process.
"""

from pathlib import Path
from typing import Any, Callable
import os
import subprocess
import sys

from srstudio.core.models import StudioProject

from .studio_bridge import StudioBridgeLaunchResult, discover_packaged_host, prepare_studio_project

SUPPORTED_DIRECT_SOURCES = {".pptx", ".xlsx", ".xlsm", ".srscene", ".zip"}


def launch_graphics_source(
    source: str | Path,
    data_dir: str | Path,
    *,
    graphics_api: str = "auto",
    process_factory: Callable[..., Any] = subprocess.Popen,
) -> StudioBridgeLaunchResult:
    """Open/import a real source directly in the G2 host."""

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"Arquivo não encontrado: {path}",
            package_path=str(path),
            graphics_api=graphics_api,
        )
    if path.suffix.lower() not in SUPPORTED_DIRECT_SOURCES:
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"Formato não suportado pelo fluxo direto do Studio de Encartes G2: {path.suffix or '<sem extensão>'}",
            package_path=str(path),
            graphics_api=graphics_api,
        )

    return _launch_host(
        path,
        data_dir=Path(data_dir),
        graphics_api=graphics_api,
        project_name=path.stem,
        source_project_id="",
        process_factory=process_factory,
        message_prefix="Studio de Encartes G2 aberto",
    )


def launch_studio_project(
    project: StudioProject,
    data_dir: str | Path,
    *,
    graphics_api: str = "auto",
    process_factory: Callable[..., Any] = subprocess.Popen,
) -> StudioBridgeLaunchResult:
    """Open the current SR Studio project in G2 without a feature flag."""

    try:
        prepared = prepare_studio_project(project, data_dir, graphics_api=graphics_api)
    except Exception as exc:
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"Falha ao preparar o projeto atual para o Studio de Encartes G2: {exc}",
            graphics_api=graphics_api,
        )

    gate_note = "gate aprovado" if prepared.gate.ready else f"gate {prepared.gate.score}/100 em validação"
    session_note = " · sessão G2 preservada" if prepared.reused_session else ""
    result = _launch_host(
        prepared.package_path,
        data_dir=Path(data_dir),
        graphics_api=prepared.graphics_api,
        project_name=project.name,
        source_project_id=str(project.id or ""),
        process_factory=process_factory,
        message_prefix=f"Studio de Encartes G2 aberto · {gate_note}{session_note}",
    )
    if not result.launched:
        return StudioBridgeLaunchResult(
            ok=result.ok,
            launched=False,
            message=result.message,
            package_path=str(prepared.package_path),
            gate_score=prepared.gate.score,
            graphics_api=prepared.graphics_api,
            pid=result.pid,
            reused_session=prepared.reused_session,
        )
    return StudioBridgeLaunchResult(
        ok=True,
        launched=True,
        message=result.message,
        package_path=str(prepared.package_path),
        gate_score=prepared.gate.score,
        graphics_api=prepared.graphics_api,
        pid=result.pid,
        reused_session=prepared.reused_session,
    )


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


def _launch_host(
    source: Path,
    *,
    data_dir: Path,
    graphics_api: str,
    project_name: str,
    source_project_id: str,
    process_factory: Callable[..., Any],
    message_prefix: str,
) -> StudioBridgeLaunchResult:
    command = _host_command()
    if not command:
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message="Studio de Encartes G2 não está instalado no pacote atual do SR Studio.",
            package_path=str(source),
            graphics_api=graphics_api,
        )

    if _uses_current_python(command):
        from .qt_host import qt_quick_available

        if not qt_quick_available():
            return StudioBridgeLaunchResult(
                ok=False,
                launched=False,
                message="PySide6/Qt Quick não está disponível neste ambiente do SR Studio.",
                package_path=str(source),
                graphics_api=graphics_api,
            )

    args = [*command, str(source), "--graphics-api", graphics_api]
    if project_name:
        args.extend(["--project-name", project_name])

    env = os.environ.copy()
    env["SR_GRAPHICS_ENGINE_2_BRIDGE"] = "1"
    # Reuse the shell's existing persistent root. The child host must never
    # invent a second Image Database location.
    env["SR_STUDIO_DATA_DIR"] = str(Path(data_dir).expanduser().resolve())
    if source_project_id:
        env["SR_GRAPHICS_ENGINE_2_SOURCE_PROJECT"] = source_project_id
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
            message=f"Não foi possível iniciar o Studio de Encartes G2: {exc}",
            package_path=str(source),
            graphics_api=graphics_api,
        )

    return StudioBridgeLaunchResult(
        ok=True,
        launched=True,
        message=f"{message_prefix} · processo isolado.",
        package_path=str(source),
        graphics_api=graphics_api,
        pid=int(getattr(process, "pid", 0) or 0),
    )
