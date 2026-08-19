from __future__ import annotations

"""Primary SR Studio -> Graphics Engine 2 activation bridge.

This module promotes the already-certified separated Qt host to the normal
Encartes Studio flow without changing the import pipeline.  PPTX/Canva exports
are passed to the host as the original source path, so ``qt_host`` continues to
own ``GraphicsImportService -> UnifiedImportPipeline -> SR Scene 2``.

The legacy ``studio_bridge`` remains responsible for runtime discovery,
persistent ``.srscene`` snapshots and compatibility sync.  No Qt objects are
created inside the Tk process.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import os
import subprocess
import sys
import tempfile

from srstudio.core.models import StudioProject

from .studio_bridge import (
    StudioBridgeLaunchResult,
    discover_packaged_host,
    prepare_studio_project,
)

SUPPORTED_DIRECT_SOURCES = {".pptx", ".xlsx", ".xlsm", ".srscene", ".zip"}


def launch_graphics_source(
    source: str | Path,
    data_dir: str | Path,
    *,
    graphics_api: str = "auto",
    process_factory: Callable[..., Any] = subprocess.Popen,
) -> StudioBridgeLaunchResult:
    """Open/import a real source directly in the G2 host.

    PPTX is deliberately *not* converted to ``StudioProject`` here.  Passing the
    original source to ``srstudio.graphics2.entrypoint`` preserves the normal G2
    import chain and all Graphics2-specific PPTX enrichment passes.
    """

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
    """Open the current SR Studio project in G2 without a feature flag.

    This is the production entrypoint.  ``launch_studio_project_if_enabled`` in
    ``studio_bridge`` is retained for historical callers and feature-flag
    compatibility; the full Studio shell no longer depends on that flag.
    """

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


def _launch_log_path() -> Path:
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        root = Path(local_app_data) / "SRStudio" / "logs"
    else:
        root = Path(tempfile.gettempdir()) / "SRStudio" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root / "g2-launch.log"


def _launch_host(
    source: Path,
    *,
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
    if source_project_id:
        env["SR_GRAPHICS_ENGINE_2_SOURCE_PROJECT"] = source_project_id

    log_path = _launch_log_path()
    log_handle = None
    try:
        log_handle = log_path.open("a", encoding="utf-8", errors="replace")
        stamp = datetime.now(timezone.utc).isoformat()
        log_handle.write(f"\n[{stamp}] launching G2: {args!r}\n")
        log_handle.flush()
        kwargs: dict[str, Any] = {
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": log_handle,
            "stderr": log_handle,
        }
        if os.name == "nt":
            kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        else:
            kwargs["start_new_session"] = True

        process = process_factory(args, **kwargs)

        # For the real production subprocess, an immediate exit means the G2 UI
        # never became usable.  Do not report success merely because Popen()
        # returned a PID.  Test/fake process factories are intentionally exempt.
        if process_factory is subprocess.Popen and hasattr(process, "wait"):
            try:
                exit_code = process.wait(timeout=1.25)
            except subprocess.TimeoutExpired:
                exit_code = None
            if exit_code is not None:
                log_handle.write(f"G2 exited during startup with code {exit_code}.\n")
                log_handle.flush()
                return StudioBridgeLaunchResult(
                    ok=False,
                    launched=False,
                    message=(
                        "O Studio de Encartes G2 encerrou durante a inicialização "
                        f"(código {exit_code}). Diagnóstico: {log_path}"
                    ),
                    package_path=str(source),
                    graphics_api=graphics_api,
                    pid=int(getattr(process, "pid", 0) or 0),
                )
    except Exception as exc:
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"Não foi possível iniciar o Studio de Encartes G2: {exc}. Diagnóstico: {log_path}",
            package_path=str(source),
            graphics_api=graphics_api,
        )
    finally:
        if log_handle is not None:
            try:
                log_handle.close()
            except OSError:
                pass

    return StudioBridgeLaunchResult(
        ok=True,
        launched=True,
        message=f"{message_prefix} · processo isolado · log: {log_path}.",
        package_path=str(source),
        graphics_api=graphics_api,
        pid=int(getattr(process, "pid", 0) or 0),
    )