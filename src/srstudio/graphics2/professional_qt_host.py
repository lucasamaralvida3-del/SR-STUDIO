from __future__ import annotations

"""Safe opt-in Qt host for the professional Studio de Encartes actions.

The stable ``qt_host`` remains untouched. This wrapper temporarily injects the
ProfessionalGraphicsCommandRouter and a contextual ProfessionalInspector into
the already-tested host module while the professional editor flow is validated.
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
    """Enable professional routing plus the opt-in contextual QML inspector."""
    previous_router = base.GraphicsCommandRouter
    previous_attach = base._attach_context_qml_tool
    attached_professional_objects: list[object] = []

    def attach_with_professional_inspector(engine, root_window, qml_path: Path, **kwargs):
        result = previous_attach(engine, root_window, qml_path, **kwargs)
        if not attached_professional_objects:
            professional_qml = Path(qml_path).with_name("ProfessionalInspector.qml")
            component, tool = previous_attach(engine, root_window, professional_qml, **kwargs)
            attached_professional_objects.extend((component, tool))
        return result

    base.GraphicsCommandRouter = ProfessionalGraphicsCommandRouter
    base._attach_context_qml_tool = attach_with_professional_inspector
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
