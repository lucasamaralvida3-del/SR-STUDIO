from __future__ import annotations

"""Safe opt-in Qt host for the professional Studio de Encartes actions.

The stable ``qt_host`` remains untouched. This wrapper temporarily injects the
ProfessionalGraphicsCommandRouter into the already-tested host module while the
professional editor flow is validated in CI and real flyers. Once the opt-in
host proves itself, Codex can make the final two-line host switch with evidence
instead of rewriting the host blindly.
"""

from contextlib import contextmanager
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


def launch_qt_quick_editor(*args, **kwargs) -> int:
    with professional_router_enabled():
        return base.launch_qt_quick_editor(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    # base.main resolves base.launch_qt_quick_editor at call time, so patch both
    # router construction and launch entrypoint only for the duration of this
    # opt-in process.
    previous_launch = base.launch_qt_quick_editor
    with professional_router_enabled():
        base.launch_qt_quick_editor = previous_launch
        try:
            return base.main(argv)
        finally:
            base.launch_qt_quick_editor = previous_launch


# Re-export read-only diagnostics/probe helpers so test scripts can use the
# professional host without importing implementation details from qt_host.
build_parser = base.build_parser
load_launch_context = base.load_launch_context
probe_graphics_api = base.probe_graphics_api
qt_quick_available = base.qt_quick_available


if __name__ == "__main__":
    raise SystemExit(main())
