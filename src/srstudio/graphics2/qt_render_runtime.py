from __future__ import annotations

"""Runtime seguro para renderização Qt fora do editor interativo.

QImage/QPainter parecem headless, porém texto, fontes e alguns recursos do Qt
consultam QFontDatabase e exigem uma QGuiApplication viva. Sem ela, um processo
CLI/pytest pode ser abortado pelo próprio Qt antes que Python consiga lançar uma
exceção. O host Qt normal já possui uma aplicação; nesse caso nada é criado.
"""

from threading import RLock
from typing import Any

_APP_LOCK = RLock()
_OWNED_APP: Any | None = None


def ensure_qt_gui_application() -> Any:
    """Retorna a aplicação Qt atual ou cria uma mínima para render headless."""

    global _OWNED_APP
    from PySide6.QtGui import QGuiApplication

    current = QGuiApplication.instance()
    if current is not None:
        return current

    with _APP_LOCK:
        current = QGuiApplication.instance()
        if current is None:
            # Manter uma referência Python é importante: deixar a instância
            # temporária ser coletada pode invalidar QFontDatabase no meio de
            # um lote de exportações.
            _OWNED_APP = QGuiApplication(["SR Graphics Engine 2 Renderer"])
            current = _OWNED_APP
    return current


def install_headless_renderer_guard(renderer_module: Any) -> None:
    """Protege render_png/render_pdf sem mudar suas assinaturas públicas."""

    if bool(getattr(renderer_module, "_sr_headless_guard_installed", False)):
        return

    original_png = renderer_module.render_png
    original_pdf = renderer_module.render_pdf

    def render_png(*args: Any, **kwargs: Any):
        ensure_qt_gui_application()
        return original_png(*args, **kwargs)

    def render_pdf(*args: Any, **kwargs: Any):
        ensure_qt_gui_application()
        return original_pdf(*args, **kwargs)

    render_png.__name__ = original_png.__name__
    render_png.__doc__ = original_png.__doc__
    render_png.__module__ = original_png.__module__
    render_pdf.__name__ = original_pdf.__name__
    render_pdf.__doc__ = original_pdf.__doc__
    render_pdf.__module__ = original_pdf.__module__

    renderer_module.render_png = render_png
    renderer_module.render_pdf = render_pdf
    renderer_module._sr_headless_guard_installed = True
