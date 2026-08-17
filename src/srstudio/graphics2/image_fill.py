from __future__ import annotations

"""Geometria compartilhada para ``a:stretch/a:fillRect`` do DrawingML.

No PPTX exportado pelo Canva, muitas fotografias não são ``p:pic`` simples:
viram preenchimentos de imagem dentro de formas. O ``fillRect`` define onde a
imagem inteira (ou o ``srcRect`` já recortado) deve ser esticada em relação à
caixa da forma. Valores negativos representam *outset* e, portanto, fazem a
imagem ultrapassar a caixa antes de ela ser recortada pela forma.

Este módulo é deliberadamente independente de Qt para que importador, preview e
renderer usem o mesmo cálculo e possam ser validados em Linux sem PySide6.
"""

from dataclasses import dataclass
from typing import Any
import math


@dataclass(slots=True, frozen=True)
class FillDestination:
    x: float
    y: float
    width: float
    height: float

    @property
    def valid(self) -> bool:
        return self.width > 1e-9 and self.height > 1e-9


def has_drawingml_fill_rect(value: object) -> bool:
    """Retorna True inclusive para ``fillRect`` explícito com offsets zero."""

    if not isinstance(value, dict) or not value:
        return False
    return any(key in value for key in ("l", "t", "r", "b", "left", "top", "right", "bottom"))


def normalize_fill_rect(value: object) -> dict[str, float]:
    """Normaliza offsets para frações da largura/altura da forma.

    O leitor PPTX atual já converte unidades DrawingML (1/100000) para fração.
    Para pacotes SR Scene mais antigos ou payloads produzidos por integrações,
    valores claramente em escala DrawingML também são aceitos.
    """

    raw = value if isinstance(value, dict) else {}
    aliases = {
        "l": ("l", "left"),
        "t": ("t", "top"),
        "r": ("r", "right"),
        "b": ("b", "bottom"),
    }
    normalized: dict[str, float] = {}
    for canonical, keys in aliases.items():
        item: Any = 0.0
        for key in keys:
            if key in raw:
                item = raw.get(key)
                break
        try:
            number = float(item or 0.0)
        except (TypeError, ValueError):
            number = 0.0
        if not math.isfinite(number):
            number = 0.0
        # Frações reais normalmente ficam em torno de -1..1. Valores como
        # -30959 são a representação OOXML em 1/100000.
        if abs(number) > 10.0:
            number /= 100000.0
        normalized[canonical] = number
    return normalized


def drawingml_fill_destination(
    width: float,
    height: float,
    fill_rect: object,
    *,
    mirror_x: bool = False,
    mirror_y: bool = False,
) -> FillDestination:
    """Calcula o retângulo local onde o BLIP deve ser esticado.

    ``l``/``t`` deslocam as bordas esquerda/superior para dentro quando
    positivos; ``r``/``b`` deslocam as bordas direita/inferior para dentro.
    Valores negativos expandem o retângulo para fora. Espelhamento é opcional e
    é útil no provider Qt Quick, que aplica o flip final depois da composição.
    """

    try:
        w = max(0.0, float(width))
        h = max(0.0, float(height))
    except (TypeError, ValueError):
        w = h = 0.0
    if not math.isfinite(w):
        w = 0.0
    if not math.isfinite(h):
        h = 0.0

    rect = normalize_fill_rect(fill_rect)
    left = rect["l"] * w
    top = rect["t"] * h
    right = w - rect["r"] * w
    bottom = h - rect["b"] * h

    if mirror_x:
        left, right = w - right, w - left
    if mirror_y:
        top, bottom = h - bottom, h - top

    result = FillDestination(left, top, right - left, bottom - top)
    if result.valid:
        return result
    # Um fillRect degenerado não deve apagar silenciosamente a fotografia.
    return FillDestination(0.0, 0.0, w, h)
