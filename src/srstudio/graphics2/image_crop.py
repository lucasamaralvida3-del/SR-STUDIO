from __future__ import annotations

"""Contrato único de crop para preview Qt, renderer e edição do SR Scene 2.

Os valores são frações da imagem-fonte, no intervalo 0..1. O contrato mantém
uma área mínima visível e aceita tanto as chaves compactas do OOXML (l/t/r/b)
quanto nomes longos. Nenhuma camada gráfica deve implementar sua própria regra
de clamp: preview, exportação e editor precisam enxergar exatamente o mesmo
retângulo-fonte.
"""

from dataclasses import dataclass
from typing import Any, Mapping

MAX_CROP_SIDE = 0.98
MAX_CROP_TOTAL = 0.995


@dataclass(slots=True, frozen=True)
class CropInsets:
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    @property
    def empty(self) -> bool:
        return max(self.left, self.top, self.right, self.bottom) <= 1e-9

    @property
    def width_fraction(self) -> float:
        return max(1.0 - MAX_CROP_TOTAL, 1.0 - self.left - self.right)

    @property
    def height_fraction(self) -> float:
        return max(1.0 - MAX_CROP_TOTAL, 1.0 - self.top - self.bottom)

    def to_dict(self) -> dict[str, float]:
        return {
            "l": float(self.left),
            "t": float(self.top),
            "r": float(self.right),
            "b": float(self.bottom),
        }


def normalize_crop(value: Mapping[str, Any] | CropInsets | None) -> CropInsets:
    """Normaliza qualquer payload de crop e impede retângulos vazios/invertidos."""

    if isinstance(value, CropInsets):
        left, top, right, bottom = value.left, value.top, value.right, value.bottom
    else:
        raw = value or {}
        left = _number(raw.get("l", raw.get("left", 0.0)))
        top = _number(raw.get("t", raw.get("top", 0.0)))
        right = _number(raw.get("r", raw.get("right", 0.0)))
        bottom = _number(raw.get("b", raw.get("bottom", 0.0)))

    left, right = _normalize_axis(left, right)
    top, bottom = _normalize_axis(top, bottom)
    return CropInsets(left, top, right, bottom)


def update_crop(
    current: Mapping[str, Any] | CropInsets | None,
    *,
    left: float | None = None,
    top: float | None = None,
    right: float | None = None,
    bottom: float | None = None,
    reset: bool = False,
) -> CropInsets:
    """Atualiza parcialmente o crop preservando a borda oposta quando possível."""

    if reset:
        return CropInsets()
    base = normalize_crop(current)
    values = {
        "left": base.left if left is None else _clamp(left),
        "top": base.top if top is None else _clamp(top),
        "right": base.right if right is None else _clamp(right),
        "bottom": base.bottom if bottom is None else _clamp(bottom),
    }

    values["left"], values["right"] = _normalize_axis_with_priority(
        values["left"],
        values["right"],
        priority="left" if left is not None and right is None else "right" if right is not None and left is None else "",
    )
    values["top"], values["bottom"] = _normalize_axis_with_priority(
        values["top"],
        values["bottom"],
        priority="top" if top is not None and bottom is None else "bottom" if bottom is not None and top is None else "",
    )
    return CropInsets(values["left"], values["top"], values["right"], values["bottom"])


def crop_pixel_box(
    width: int,
    height: int,
    crop: Mapping[str, Any] | CropInsets | None,
) -> tuple[int, int, int, int]:
    """Converte frações normalizadas em um retângulo seguro, sempre >= 1×1."""

    source_width = max(1, int(width))
    source_height = max(1, int(height))
    value = normalize_crop(crop)

    x1 = min(source_width - 1, max(0, round(source_width * value.left)))
    y1 = min(source_height - 1, max(0, round(source_height * value.top)))
    x2 = min(source_width, max(x1 + 1, round(source_width * (1.0 - value.right))))
    y2 = min(source_height, max(y1 + 1, round(source_height * (1.0 - value.bottom))))
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def _number(value: Any) -> float:
    try:
        return _clamp(float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return min(MAX_CROP_SIDE, max(0.0, float(value)))


def _normalize_axis(first: float, second: float) -> tuple[float, float]:
    return _normalize_axis_with_priority(_clamp(first), _clamp(second), priority="")


def _normalize_axis_with_priority(first: float, second: float, *, priority: str) -> tuple[float, float]:
    total = first + second
    if total <= MAX_CROP_TOTAL:
        return first, second
    if priority in {"left", "top"}:
        return max(0.0, MAX_CROP_TOTAL - second), second
    if priority in {"right", "bottom"}:
        return first, max(0.0, MAX_CROP_TOTAL - first)
    if total <= 1e-12:
        return 0.0, 0.0
    scale = MAX_CROP_TOTAL / total
    return first * scale, second * scale
