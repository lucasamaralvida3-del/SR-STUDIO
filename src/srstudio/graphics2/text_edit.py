from __future__ import annotations

"""Professional text-style editing helpers for the G2 flyer editor."""

from typing import Any, TYPE_CHECKING

from .model import NodeKind

if TYPE_CHECKING:
    from .operations import GraphicsSession


_ALLOWED_ALIGN = {"left", "center", "right", "justify"}
_ALLOWED_VERTICAL = {"top", "center", "bottom"}


def update_text_style(
    session: "GraphicsSession",
    node_id: str,
    *,
    font_family: str | None = None,
    font_size: float | None = None,
    font_weight: int | None = None,
    italic: bool | None = None,
    color: str | None = None,
    align: str | None = None,
    vertical_align: str | None = None,
    letter_spacing: float | None = None,
    line_spacing: float | None = None,
    opacity: float | None = None,
) -> bool:
    """Update supported text properties atomically without changing geometry."""

    node = session.page.node(str(node_id))
    if node is None or node.kind is not NodeKind.TEXT or session.effective_locked(node.id):
        return False

    changes: dict[str, Any] = {}
    if font_family is not None:
        value = str(font_family).strip()
        if value:
            changes["font_family"] = value
    if font_size is not None:
        changes["font_size"] = max(1.0, min(2000.0, float(font_size)))
        changes.setdefault("font_size_unit", "pt")
    if font_weight is not None:
        changes["font_weight"] = max(100, min(1000, int(font_weight)))
    if italic is not None:
        changes["italic"] = bool(italic)
    if color is not None:
        value = str(color).strip()
        if value:
            changes["color"] = value
    if align is not None:
        value = str(align).strip().lower()
        if value not in _ALLOWED_ALIGN:
            raise ValueError(f"Alinhamento horizontal inválido: {align}")
        changes["align"] = value
    if vertical_align is not None:
        value = str(vertical_align).strip().lower()
        if value not in _ALLOWED_VERTICAL:
            raise ValueError(f"Alinhamento vertical inválido: {vertical_align}")
        changes["vertical_align"] = value
    if letter_spacing is not None:
        changes["letter_spacing"] = float(letter_spacing)
    reset_fixed_line_spacing = line_spacing is not None
    if line_spacing is not None:
        changes["line_spacing_percent"] = max(0.1, float(line_spacing))
    if opacity is not None:
        opacity_value = max(0.0, min(1.0, float(opacity)))
    else:
        opacity_value = None

    if not changes and opacity_value is None:
        return False

    with session.transaction("Formatar texto"):
        if reset_fixed_line_spacing:
            node.style.pop("line_spacing_px", None)
        node.style.update(changes)
        if opacity_value is not None:
            node.opacity = opacity_value
    return True
