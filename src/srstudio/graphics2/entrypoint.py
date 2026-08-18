from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile

import srstudio
from srstudio.diagnostics.crash_guard import CrashGuard

from . import ENGINE_VERSION
from . import qt_host

LOGGER_NAME = "srstudio.graphics2"


def diagnostics_root() -> Path:
    configured = str(os.environ.get("SR_STUDIO_G2_DIAGNOSTICS_ROOT") or "").strip()
    preferred = Path(configured).expanduser() if configured else Path.home() / ".srstudio5" / "diagnostics-g2"
    fallback = Path(tempfile.gettempdir()) / "SRStudio" / "diagnostics-g2"
    last_error: OSError | None = None
    for candidate in (preferred, fallback):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError as exc:
            last_error = exc
    raise OSError(f"Não foi possível criar diretório de diagnóstico G2: {last_error}")


def configure_logging(root: Path | None = None) -> tuple[logging.Logger, Path]:
    target_root = (root or diagnostics_root()).resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    log_path = target_root / "graphics2.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    marker = str(log_path)
    if not any(getattr(handler, "_srstudio_log_path", "") == marker for handler in logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler._srstudio_log_path = marker  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logging.captureWarnings(True)
    return logger, log_path


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--release-smoke" in raw:
        raw.remove("--release-smoke")
        from .release_smoke import main as smoke_main

        return smoke_main(raw)

    logger, log_path = configure_logging()
    action = "startup"
    source = ""
    module = "srstudio.graphics2.entrypoint"
    guard = CrashGuard(
        diagnostics_root(),
        version=f"srstudio={srstudio.__version__}; graphics2={ENGINE_VERSION}",
    )
    guard.install(lambda: source, lambda: action, lambda: module)

    try:
        args = qt_host.build_parser().parse_args(raw)
        source = str(args.source or "")
        logger.info(
            "startup version=%s engine=%s source=%s graphics_api=%s frozen=%s",
            srstudio.__version__,
            ENGINE_VERSION,
            source or "<new>",
            args.graphics_api,
            bool(getattr(sys, "frozen", False)),
        )
        if args.probe_graphics_api:
            action = "graphics-api-probe"
            module = "srstudio.graphics2.qt_host.probe_graphics_api"
            probe = qt_host.probe_graphics_api(args.graphics_api)
            print(f"SR Graphics Engine 2 GPU: solicitado={probe.requested} | resolvido={probe.resolved}")
            logger.info("graphics probe requested=%s resolved=%s", probe.requested, probe.resolved)
            return 0

        action = "load-project"
        module = "srstudio.graphics2.qt_host.load_launch_context"
        context = qt_host.load_launch_context(args.source, project_name=args.project_name)
        action = "qt-editor"
        module = "srstudio.graphics2.qt_host.launch_qt_quick_editor"
        return qt_host.launch_qt_quick_editor(
            context.document,
            graphics_api=args.graphics_api,
            launch_context=context,
        )
    except Exception as exc:
        logger.exception("fatal action=%s source=%s module=%s", action, source or "<new>", module)
        guard.capture(
            type(exc),
            exc,
            exc.__traceback__,
            source,
            action=action,
            module=module,
        )
        print(
            f"SR Graphics Engine 2: ERRO: {exc} | diagnóstico: {log_path}",
            file=sys.stderr,
        )
        return 2
    finally:
        guard.uninstall()


if __name__ == "__main__":
    raise SystemExit(main())
