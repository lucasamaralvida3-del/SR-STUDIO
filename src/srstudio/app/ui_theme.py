"""Shared visual theme helpers for the SR Studio interfaces.

Only widget chrome passes through this module. Scene colors remain untouched.
"""

from __future__ import annotations

try:
    from tkinter import TclError
except ImportError:  # The headless test runtime has no Tcl installation.
    TclError = RuntimeError


def normalized_theme(value: object) -> str:
    return "dark" if value == "dark" else "light"


_EXACT = {
    "background": {
        "#FFFFFF": "#111A28",
        "#F3F6FA": "#101827",
        "#F8FAFD": "#172235",
        "#F3F7FC": "#202D42",
        "#EAF0F8": "#27364B",
        "#1559D6": "#1559D6",
    },
    "foreground": {
        "#152033": "#E8EFFA",
        "#657186": "#B6C4D8",
        "#8C98AA": "#9EADC3",
        "#FFFFFF": "#FFFFFF",
    },
    "border": {
        "#DFE6EF": "#344258",
        "#C9D4E3": "#455570",
    },
}


def color_for_theme(color: str, role: str, theme: str) -> str:
    """Return a dark UI swatch for a Tk/QML color, leaving artwork alone."""
    if normalized_theme(theme) == "light" or role == "artwork":
        return color
    named = {"white": "#FFFFFF", "black": "#000000"}
    source = named.get(color.lower(), color).upper()
    if not source.startswith("#") or len(source) not in (7, 9):
        return color
    try:
        rgb = tuple(int(source[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return color
    alpha = source[7:] if len(source) == 9 else ""
    if role == "auto":
        luminance = sum(rgb) / 3
        role = "background" if luminance >= 198 else "foreground"
    exact = _EXACT.get(role, {}).get(source[:7])
    if exact is not None:
        return exact + alpha
    high, low = max(rgb), min(rgb)
    luminance = sum(rgb) / 3
    saturation = high - low
    if role == "background":
        if luminance < 175:
            return color
        if saturation < 22:
            return ("#1D293B" if luminance < 239 else "#172235") + alpha
        # Pale colored badges become tinted dark surfaces.
        tinted = tuple(round(25 + channel * 0.16) for channel in rgb)
        return "#" + "".join(f"{channel:02X}" for channel in tinted) + alpha
    if role == "border":
        return ("#344258" if luminance >= 175 else "#536580") + alpha
    if role == "foreground":
        if luminance >= 180:
            return color
        if saturation < 45:
            return ("#E8EFFA" if luminance < 90 else "#B6C4D8") + alpha
        if luminance < 155:
            bright = tuple(round(channel * 0.55 + 105) for channel in rgb)
            return "#" + "".join(f"{min(255, channel):02X}" for channel in bright) + alpha
    return color


def apply_widget_theme(root, theme: str) -> None:
    """Recolor existing Tk widgets, including screens created after startup.

    Original options are recorded on each widget so switching back to light
    restores the exact pre-theme values, including custom screen colors.
    """
    roles = {
        "background": "background",
        "activebackground": "background",
        "disabledbackground": "background",
        "readonlybackground": "background",
        "selectbackground": "background",
        "troughcolor": "background",
        "foreground": "foreground",
        "activeforeground": "foreground",
        "disabledforeground": "foreground",
        "selectforeground": "foreground",
        "insertbackground": "foreground",
        "highlightbackground": "border",
        "highlightcolor": "border",
    }

    def visit(widget) -> None:
        try:
            options = widget.configure()
            original = getattr(widget, "_sr_theme_original", None)
            if original is None:
                original = {name: str(widget.cget(name)) for name in roles if name in options}
                widget._sr_theme_original = original
            else:
                applied = getattr(widget, "_sr_theme_applied", {})
                for name in original:
                    current = str(widget.cget(name))
                    if name in applied and current != applied[name] and current != original[name]:
                        original[name] = current
            updates = {
                name: color_for_theme(value, roles[name], theme)
                for name, value in original.items()
            }
            if updates:
                widget.configure(**updates)
                widget._sr_theme_applied = updates
            children = widget.winfo_children()
        except (AttributeError, RuntimeError, TclError, ValueError):
            return
        for child in children:
            visit(child)

    visit(root)


def apply_ttk_theme(style, theme: str, names: list[str], original: dict) -> None:
    """Recolor ttk style definitions while keeping their light configuration."""
    roles = {
        "background": "background", "fieldbackground": "background",
        "troughcolor": "background", "selectbackground": "background",
        "foreground": "foreground", "selectforeground": "foreground",
        "arrowcolor": "foreground", "bordercolor": "border",
        "lightcolor": "border", "darkcolor": "border",
    }
    for name in names:
        try:
            current = style.configure(name) or {}
            if name not in original:
                original[name] = (
                    {key: value for key, value in current.items() if key in roles},
                    {key: value for key, value in (style.map(name) or {}).items() if key in roles},
                )
            config, state_map = original[name]
            updates = {key: color_for_theme(str(value), roles[key], theme)
                       for key, value in config.items()}
            if updates:
                style.configure(name, **updates)
            mapped = {
                key: [(state, color_for_theme(str(value), roles[key], theme))
                      for state, value in values]
                for key, values in state_map.items()
            }
            if mapped:
                style.map(name, **mapped)
        except (TclError, ValueError):
            continue
    if normalized_theme(theme) == "dark":
        defaults = {
            "TFrame": {"background": "#101827"},
            "TLabel": {"background": "#101827", "foreground": "#E8EFFA"},
            "TButton": {"background": "#26364D", "foreground": "#E8EFFA"},
            "TCheckbutton": {"background": "#101827", "foreground": "#E8EFFA"},
            "TRadiobutton": {"background": "#101827", "foreground": "#E8EFFA"},
            "TEntry": {"fieldbackground": "#172235", "foreground": "#E8EFFA"},
            "TCombobox": {"fieldbackground": "#172235", "foreground": "#E8EFFA"},
            "Treeview": {"background": "#172235", "fieldbackground": "#172235", "foreground": "#E8EFFA"},
            "Treeview.Heading": {"background": "#26364D", "foreground": "#E8EFFA"},
            "TLabelframe": {"background": "#101827", "foreground": "#E8EFFA"},
            "TLabelframe.Label": {"background": "#101827", "foreground": "#E8EFFA"},
        }
        for name, values in defaults.items():
            if name in names:
                style.configure(name, **values)
