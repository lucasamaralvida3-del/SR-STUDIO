from __future__ import annotations

"""Primary SR Studio -> Graphics Engine 2 activation bridge.

The full Studio shell has one Encartes destination: the separated Qt/G2 host.
This module never selects an alternative editor. Compatibility snapshot/sync
helpers remain in ``studio_bridge`` because they are shared data infrastructure,
not product routing.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import os
import subprocess
import sys
import tempfile

from srstudio import __version__
from srstudio.core.models import StudioProject

from .studio_bridge import (
    HOST_EXE_NAME,
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
            message=f"Formato não suportado pelo Studio de Encartes G2: {path.suffix or '<sem extensão>'}",
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
    """Open the current SR Studio project in G2 without a feature flag."""

    try:
        prepared = prepare_studio_project(project, data_dir, graphics_api=graphics_api)
    except Exception as exc:
        reason = f"Falha ao preparar o projeto atual para o G2: {exc}"
        diagnostic = _diagnostic_text(
            reason=reason,
            source=Path(data_dir),
            graphics_api=graphics_api,
            command=[],
            exception=exc,
        )
        log_path = _write_diagnostic(diagnostic)
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"{diagnostic}\nLog: {log_path}",
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


def _host_search_paths() -> list[str]:
    candidates: list[Path] = []
    explicit = str(os.environ.get("SR_GRAPHICS_ENGINE_2_HOST") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())

    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_dir / "Graphics2Host" / HOST_EXE_NAME,
            executable_dir / HOST_EXE_NAME,
            Path(__file__).resolve().parents[3] / "Graphics2Host" / HOST_EXE_NAME,
        ]
    )
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        candidates.append(Path(local_app_data) / "SRStudio" / "App" / "Graphics2Host" / HOST_EXE_NAME)

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        unique.append(str(resolved))
    return unique


def _diagnostic_text(
    *,
    reason: str,
    source: Path,
    graphics_api: str,
    command: list[str],
    exception: Exception | None = None,
) -> str:
    if command:
        if _uses_current_python(command):
            found = "development: python -m srstudio.graphics2.entrypoint"
        else:
            found = str(command[0])
    else:
        found = "NÃO ENCONTRADO"
    searched = _host_search_paths()
    lines = [
        "Não foi possível iniciar o Studio de Encartes G2.",
        f"Motivo: {reason}",
        f"Host procurado: {' | '.join(searched) if searched else '<nenhum caminho calculado>'}",
        f"Host encontrado: {found}",
        f"Source: {source}",
        f"SR Studio source/version: {__version__}",
        (
            "Launcher/runtime: "
            f"executable={sys.executable} · frozen={bool(getattr(sys, 'frozen', False))} · "
            f"python={sys.version.split()[0]} · platform={sys.platform} · graphics_api={graphics_api}"
        ),
    ]
    if exception is not None:
        lines.append(f"Exception: {type(exception).__name__}: {exception}")
    return "\n".join(lines)


def _write_diagnostic(text: str) -> Path:
    log_path = _launch_log_path()
    stamp = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(f"\n[{stamp}] G2 LAUNCH DIAGNOSTIC\n{text}\n")
    return log_path


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
        diagnostic = _diagnostic_text(
            reason="SRGraphicsEngine2Host.exe não foi encontrado ou validado no pacote atual.",
            source=source,
            graphics_api=graphics_api,
            command=command,
        )
        log_path = _write_diagnostic(diagnostic)
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"{diagnostic}\nLog: {log_path}",
            package_path=str(source),
            graphics_api=graphics_api,
        )

    if _uses_current_python(command):
        from .qt_host import qt_quick_available

        if not qt_quick_available():
            diagnostic = _diagnostic_text(
                reason="PySide6/Qt Quick não está disponível neste runtime.",
                source=source,
                graphics_api=graphics_api,
                command=command,
            )
            log_path = _write_diagnostic(diagnostic)
            return StudioBridgeLaunchResult(
                ok=False,
                launched=False,
                message=f"{diagnostic}\nLog: {log_path}",
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
        launch_context = _diagnostic_text(
            reason="launch requested",
            source=source,
            graphics_api=graphics_api,
            command=command,
        )
        log_handle.write(f"\n[{stamp}] launching G2\n{launch_context}\nargs={args!r}\n")
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

        if process_factory is subprocess.Popen and hasattr(process, "wait"):
            try:
                exit_code = process.wait(timeout=1.25)
            except subprocess.TimeoutExpired:
                exit_code = None
            if exit_code is not None:
                reason = f"O processo G2 encerrou durante a inicialização com código {exit_code}."
                diagnostic = _diagnostic_text(
                    reason=reason,
                    source=source,
                    graphics_api=graphics_api,
                    command=command,
                )
                log_handle.write(f"{diagnostic}\n")
                log_handle.flush()
                return StudioBridgeLaunchResult(
                    ok=False,
                    launched=False,
                    message=f"{diagnostic}\nLog: {log_path}",
                    package_path=str(source),
                    graphics_api=graphics_api,
                    pid=int(getattr(process, "pid", 0) or 0),
                )
    except Exception as exc:
        diagnostic = _diagnostic_text(
            reason="Exceção ao criar/iniciar o processo do G2.",
            source=source,
            graphics_api=graphics_api,
            command=command,
            exception=exc,
        )
        try:
            if log_handle is not None:
                log_handle.write(f"{diagnostic}\n")
                log_handle.flush()
            else:
                _write_diagnostic(diagnostic)
        except OSError:
            pass
        return StudioBridgeLaunchResult(
            ok=False,
            launched=False,
            message=f"{diagnostic}\nLog: {log_path}",
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