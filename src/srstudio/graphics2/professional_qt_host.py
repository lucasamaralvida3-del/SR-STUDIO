from __future__ import annotations

"""Safe opt-in Qt host for the professional Studio de Encartes actions.

The stable ``qt_host`` remains untouched. This wrapper temporarily injects the
ProfessionalGraphicsCommandRouter plus professional contextual/recovery QML
controls into the already-tested host module while the flow is validated.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import qt_host as base
from .professional_command_router import ProfessionalGraphicsCommandRouter


@contextmanager
def professional_router_enabled() -> Iterator[None]:
    """Temporarily route Qt host commands through the professional G2 router."""
    previous = base.GraphicsCommandRouter
    base.GraphicsCommandRouter = ProfessionalGraphicsCommandRouter
    try:
        yield
    finally:
        base.GraphicsCommandRouter = previous


@contextmanager
def professional_host_enabled() -> Iterator[None]:
    """Enable professional routing plus opt-in inspector/recovery QML controls."""
    previous_router = base.GraphicsCommandRouter
    previous_attach = base._attach_context_qml_tool
    attached_professional_objects: list[object] = []

    def attach_with_professional_tools(engine, root_window, qml_path: Path, **kwargs):
        result = previous_attach(engine, root_window, qml_path, **kwargs)
        if not attached_professional_objects:
            base_dir = Path(qml_path).parent
            for filename in ("ProfessionalInspector.qml", "ProfessionalRecovery.qml"):
                component, tool = previous_attach(
                    engine,
                    root_window,
                    base_dir / filename,
                    **kwargs,
                )
                attached_professional_objects.extend((component, tool))
        return result

    base.GraphicsCommandRouter = ProfessionalGraphicsCommandRouter
    base._attach_context_qml_tool = attach_with_professional_tools
    try:
        yield
    finally:
        base._attach_context_qml_tool = previous_attach
        base.GraphicsCommandRouter = previous_router
        attached_professional_objects.clear()


def launch_qt_quick_editor(*args, **kwargs) -> int:
    with professional_host_enabled():
        return base.launch_qt_quick_editor(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    with professional_host_enabled():
        return base.main(argv)


build_parser = base.build_parser
load_launch_context = base.load_launch_context
probe_graphics_api = base.probe_graphics_api
qt_quick_available = base.qt_quick_available


if __name__ == "__main__":
    raise SystemExit(main())
