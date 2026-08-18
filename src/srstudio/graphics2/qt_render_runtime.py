from __future__ import annotations

"""Runtime seguro para renderização Qt fora do editor interativo.

QImage/QPainter parecem headless, porém texto, fontes e alguns recursos do Qt
consultam QFontDatabase e exigem uma QGuiApplication viva. Sem ela, um processo
CLI/pytest pode ser abortado pelo próprio Qt antes que Python consiga lançar uma
exceção. O host Qt normal já possui uma aplicação; nesse caso nada é criado.

A instalação também conecta as chamadas históricas ``qt_renderer.render_*`` à
camada de output de produção. Assim o host/QML existente recebe escrita atômica,
validação pós-export, JPEG e batch sem mover a responsabilidade visual para este
módulo nem exigir alteração do editor paralelo.
"""

from threading import RLock
from typing import Any

_APP_LOCK = RLock()
_OWNED_APP: Any | None = None


class _LowLevelRendererProxy:
    """Mantém os renderizadores headless originais disponíveis ao output layer.

    ``export_output`` consome helpers visuais do módulo ``qt_renderer``. Depois
    que as APIs públicas desse módulo são redirecionadas para o pipeline seguro,
    o proxy evita recursão e continua delegando todos os helpers visuais ao
    renderer real. É deliberadamente interno ao bootstrap do pacote.
    """

    def __init__(self, renderer_module: Any, *, render_png: Any, render_pdf: Any) -> None:
        self._renderer_module = renderer_module
        self.render_png = render_png
        self.render_pdf = render_pdf

    def __getattr__(self, name: str) -> Any:
        return getattr(self._renderer_module, name)


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
    """Protege renderização headless e instala o pipeline final de saída."""

    if not bool(getattr(renderer_module, "_sr_headless_guard_installed", False)):
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
        renderer_module._sr_headless_png_renderer = render_png
        renderer_module._sr_headless_pdf_renderer = render_pdf
        renderer_module._sr_headless_guard_installed = True

    if bool(getattr(renderer_module, "_sr_production_output_guard_installed", False)):
        return

    # Import tardio evita ciclo durante o bootstrap do pacote: export_output
    # também usa ensure_qt_gui_application e os helpers privados do renderer.
    from . import export_output as output
    from .export_batch import export_raster_batch as transactional_export_raster_batch
    from .pdf_output_renderer import render_pdf as full_bleed_pdf_renderer

    headless_png = getattr(renderer_module, "_sr_headless_png_renderer", renderer_module.render_png)
    headless_pdf = getattr(renderer_module, "_sr_headless_pdf_renderer", renderer_module.render_pdf)
    output._renderer = _LowLevelRendererProxy(
        renderer_module,
        render_png=headless_png,
        render_pdf=headless_pdf,
    )
    # PDF uses the same scene renderer, but QPdfWriter page-device semantics
    # belong to the output layer. The adapter removes implicit margins and
    # paints the physical page background before applying the scene transform.
    output._renderer.render_pdf = full_bleed_pdf_renderer
    output.export_raster_batch = transactional_export_raster_batch

    # Compatibilidade: chamadas existentes do host continuam usando os nomes
    # históricos e passam a receber o contrato de produção. APIs novas ficam
    # disponíveis sem obrigar mudanças em QML/editor nesta branch paralela.
    renderer_module.render_png = output.export_png
    renderer_module.render_pdf = output.export_pdf
    renderer_module.render_jpeg = output.export_jpeg
    renderer_module.render_raster_batch = transactional_export_raster_batch
    renderer_module._sr_production_output_guard_installed = True
