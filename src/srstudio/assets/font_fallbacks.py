from __future__ import annotations


CANVA_FAMILY_FALLBACKS: dict[str, tuple[str, ...]] = {
    "anton": ("Anton", "Impact", "Arial Narrow", "Arial"),
    "high cruiser": ("High Cruiser", "Impact", "Arial Narrow", "Arial"),
    "zing rust base": ("Zing Rust Base", "Impact", "Arial Narrow", "Arial"),
    "roboto condensed": ("Roboto Condensed", "Arial Narrow", "Arial"),
    "arimo": ("Arimo", "Arial", "Segoe UI"),
    "raleway": ("Raleway", "Segoe UI", "Arial"),
    "montserrat": ("Montserrat", "Segoe UI", "Arial"),
    "poppins": ("Poppins", "Segoe UI", "Arial"),
}

PILLOW_FILE_FALLBACKS: dict[str, tuple[str, ...]] = {
    "anton": ("Anton.ttf", "impact.ttf", "arialn.ttf", "arial.ttf"),
    "high cruiser": ("impact.ttf", "arialn.ttf", "arial.ttf"),
    "zing rust base": ("impact.ttf", "arialn.ttf", "arial.ttf"),
    "roboto condensed": ("RobotoCondensed-Regular.ttf", "arialn.ttf", "arial.ttf"),
    "arimo": ("Arimo-Regular.ttf", "arial.ttf", "segoeui.ttf"),
    "raleway": ("Raleway-Regular.ttf", "segoeui.ttf", "arial.ttf"),
    "montserrat": ("Montserrat-Regular.ttf", "segoeui.ttf", "arial.ttf"),
    "poppins": ("Poppins-Regular.ttf", "segoeui.ttf", "arial.ttf"),
}


def normalize_family(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def choose_tk_family(requested: str, installed: set[str] | tuple[str, ...] | list[str]) -> str:
    """Choose an installed family while keeping Canva-like condensed metrics."""
    installed_names = {str(name) for name in installed}
    installed_lookup = {normalize_family(name): str(name) for name in installed_names}
    key = normalize_family(requested)
    candidates = CANVA_FAMILY_FALLBACKS.get(key, (requested,) if requested else ())
    for candidate in candidates:
        match = installed_lookup.get(normalize_family(candidate))
        if match:
            return match
    for generic in ("Segoe UI", "Arial", "DejaVu Sans"):
        match = installed_lookup.get(normalize_family(generic))
        if match:
            return match
    return requested or "Arial"


def pillow_font_candidates(requested: str, bold: bool = False) -> list[str]:
    key = normalize_family(requested)
    candidates: list[str] = []
    if requested and not requested.startswith("+"):
        candidates.extend((requested, f"{requested}.ttf", f"{requested}.otf"))
    candidates.extend(PILLOW_FILE_FALLBACKS.get(key, ()))
    candidates.extend(
        (
            "arialnb.ttf" if bold else "arialn.ttf",
            "arialbd.ttf" if bold else "arial.ttf",
            "segoeuib.ttf" if bold else "segoeui.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        )
    )
    return list(dict.fromkeys(name for name in candidates if name))


def canva_wrap_width(text: str, role: str, width: float) -> float:
    """Canva single-line boxes must not wrap R$, cents, units or short names.

    A missing Canva font otherwise makes Tk wrap a two-character price token into
    two lines, which is the main cause of the vertical/fragmented prices seen in
    imported flyers.
    """
    value = str(text or "")
    if not value or "\n" not in value:
        if role in {
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
        }:
            return 0.0
        if len(value) <= 32:
            return 0.0
    return max(0.0, width)
