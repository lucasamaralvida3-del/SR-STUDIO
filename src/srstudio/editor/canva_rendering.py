from __future__ import annotations

from dataclasses import dataclass


PT_TO_PX = 96.0 / 72.0


PRICE_ROLES = {
    "price_currency",
    "price_integer",
    "price_cents",
    "price_complete",
    "unit",
    "app_price_currency",
    "app_price_integer",
    "app_price_cents",
    "app_price_complete",
    "app_unit",
}


@dataclass(frozen=True, slots=True)
class CanvaTextPlacement:
    x_factor: float
    y_factor: float
    anchor: str
    justify: str


def font_pixel_size(points: float, scale: float) -> int:
    """Convert PPTX point size to the Studio's 96-DPI page pixels."""
    try:
        value = float(points)
    except (TypeError, ValueError):
        value = 0.0
    return max(4, round(max(value, 1.0) * PT_TO_PX * max(float(scale), 0.01)))


def text_placement(align: str, vertical_anchor: str) -> CanvaTextPlacement:
    horizontal = str(align or "").strip().lower()
    vertical = str(vertical_anchor or "").strip().lower()

    if horizontal in {"ctr", "center", "mid"}:
        x_factor = 0.5
        h_anchor = ""
        justify = "center"
    elif horizontal in {"r", "right"}:
        x_factor = 1.0
        h_anchor = "e"
        justify = "right"
    else:
        x_factor = 0.0
        h_anchor = "w"
        justify = "left"

    if vertical in {"ctr", "center", "mid"}:
        y_factor = 0.5
        v_anchor = ""
    elif vertical in {"b", "bottom"}:
        y_factor = 1.0
        v_anchor = "s"
    else:
        y_factor = 0.0
        v_anchor = "n"

    if not v_anchor and not h_anchor:
        anchor = "center"
    else:
        anchor = f"{v_anchor}{h_anchor}" or "center"
    return CanvaTextPlacement(x_factor=x_factor, y_factor=y_factor, anchor=anchor, justify=justify)


def should_force_single_line(element: dict) -> bool:
    text = str(element.get("text") or "")
    if "\n" in text:
        return False
    role = str(element.get("slot_role") or "")
    if role in PRICE_ROLES:
        return True
    if bool(element.get("canva_no_wrap")):
        return True
    if bool(element.get("canva_single_line")) and len(text) <= 48:
        return True
    return False


def fit_single_line_size(
    initial_px: int,
    text_width: float,
    line_height: float,
    box_width: float,
    box_height: float,
    *,
    min_px: int = 4,
    overflow_ratio: float = 1.0,
) -> int:
    """Return a proportional smaller pixel size without wrapping the text.

    The caller measures at ``initial_px``. This helper stays toolkit-agnostic so
    editor and tests can share the same policy.
    """
    size = max(min_px, int(initial_px))
    if text_width <= 0 or line_height <= 0:
        return size
    max_width = max(1.0, float(box_width) * max(float(overflow_ratio), 0.25))
    max_height = max(1.0, float(box_height) * 1.10)
    ratio = min(1.0, max_width / text_width, max_height / line_height)
    return max(min_px, int(size * ratio))


def role_overflow_ratio(role: str) -> float:
    """Canva exports split price tokens in intentionally tight text boxes."""
    value = str(role or "")
    if value in {"price_currency", "app_price_currency", "unit", "app_unit"}:
        return 1.45
    if value in {"price_cents", "app_price_cents"}:
        return 1.35
    if value in {"price_integer", "app_price_integer"}:
        return 1.18
    return 1.0


def rounded_radius(width: float, height: float, ratio: float) -> float:
    try:
        value = float(ratio)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(float(width), float(height)) * max(0.0, min(value, 0.48)))
