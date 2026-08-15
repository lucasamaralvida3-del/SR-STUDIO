from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from srstudio.app.design import COLORS, FONT


TONE_COLORS = {
    "primary": (COLORS.primary, COLORS.primary_soft),
    "success": (COLORS.success, COLORS.success_soft),
    "warning": (COLORS.warning, COLORS.warning_soft),
    "danger": (COLORS.danger, COLORS.danger_soft),
    "neutral": (COLORS.text_muted, COLORS.surface_alt),
    "purple": (COLORS.purple, COLORS.purple_soft),
}


def card(parent: tk.Widget, *, bg: str | None = None, border: bool = True) -> tk.Frame:
    background = bg or COLORS.surface
    return tk.Frame(
        parent,
        bg=background,
        highlightbackground=COLORS.border if border else background,
        highlightthickness=1 if border else 0,
        bd=0,
    )


def divider(parent: tk.Widget, *, bg: str | None = None) -> tk.Frame:
    return tk.Frame(parent, bg=bg or COLORS.border, height=1)


def pill(parent: tk.Widget, text: str, tone: str = "neutral") -> tk.Label:
    fg, bg = TONE_COLORS.get(tone, TONE_COLORS["neutral"])
    return tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        font=(FONT["family"], FONT["micro"], "bold"),
        padx=9,
        pady=4,
    )


def eyebrow(parent: tk.Widget, text: str, *, bg: str | None = None) -> tk.Label:
    background = bg or parent.cget("bg")
    return tk.Label(
        parent,
        text=text.upper(),
        bg=background,
        fg=COLORS.text_subtle,
        font=(FONT["family"], FONT["micro"], "bold"),
    )


def page_header(
    parent: tk.Widget,
    title: str,
    subtitle: str,
    *,
    action_text: str = "",
    action: Callable[[], object] | None = None,
) -> tk.Frame:
    frame = tk.Frame(parent, bg=COLORS.bg)
    left = tk.Frame(frame, bg=COLORS.bg)
    left.pack(side="left", fill="x", expand=True)
    tk.Label(
        left,
        text=title,
        bg=COLORS.bg,
        fg=COLORS.text,
        font=(FONT["family"], FONT["page_title"], "bold"),
    ).pack(anchor="w")
    tk.Label(
        left,
        text=subtitle,
        bg=COLORS.bg,
        fg=COLORS.text_muted,
        font=(FONT["family"], FONT["body"]),
    ).pack(anchor="w", pady=(4, 0))
    if action_text and action is not None:
        ttk.Button(frame, text=action_text, style="Primary.TButton", command=action).pack(side="right", padx=(16, 0))
    return frame


def metric_card(
    parent: tk.Widget,
    *,
    label: str,
    value: str,
    icon: str,
    tone: str = "primary",
    hint: str = "",
) -> tk.Frame:
    fg, soft = TONE_COLORS.get(tone, TONE_COLORS["primary"])
    frame = card(parent)
    top = tk.Frame(frame, bg=COLORS.surface)
    top.pack(fill="x", padx=16, pady=(14, 6))
    icon_box = tk.Label(
        top,
        text=icon,
        width=3,
        bg=soft,
        fg=fg,
        font=(FONT["family"], 12, "bold"),
        pady=5,
    )
    icon_box.pack(side="left")
    if hint:
        pill(top, hint, tone).pack(side="right")
    tk.Label(
        frame,
        text=str(value),
        bg=COLORS.surface,
        fg=COLORS.text,
        font=(FONT["family"], 20, "bold"),
    ).pack(anchor="w", padx=16, pady=(2, 0))
    tk.Label(
        frame,
        text=label,
        bg=COLORS.surface,
        fg=COLORS.text_muted,
        font=(FONT["family"], FONT["small"]),
    ).pack(anchor="w", padx=16, pady=(2, 14))
    return frame


def action_tile(
    parent: tk.Widget,
    *,
    title: str,
    detail: str,
    icon: str,
    command: Callable[[], object],
    tone: str = "primary",
) -> tk.Frame:
    fg, soft = TONE_COLORS.get(tone, TONE_COLORS["primary"])
    frame = card(parent)
    frame.configure(cursor="hand2")

    icon_label = tk.Label(
        frame,
        text=icon,
        width=3,
        bg=soft,
        fg=fg,
        font=(FONT["family"], 14, "bold"),
        pady=7,
        cursor="hand2",
    )
    icon_label.pack(side="left", padx=(14, 12), pady=14)

    text = tk.Frame(frame, bg=COLORS.surface, cursor="hand2")
    text.pack(side="left", fill="both", expand=True, pady=12)
    title_label = tk.Label(
        text,
        text=title,
        bg=COLORS.surface,
        fg=COLORS.text,
        font=(FONT["family"], FONT["body"], "bold"),
        anchor="w",
        cursor="hand2",
    )
    title_label.pack(fill="x")
    detail_label = tk.Label(
        text,
        text=detail,
        bg=COLORS.surface,
        fg=COLORS.text_muted,
        font=(FONT["family"], FONT["small"]),
        anchor="w",
        cursor="hand2",
    )
    detail_label.pack(fill="x", pady=(3, 0))
    arrow = tk.Label(
        frame,
        text="›",
        bg=COLORS.surface,
        fg=COLORS.text_subtle,
        font=(FONT["family"], 18),
        cursor="hand2",
    )
    arrow.pack(side="right", padx=(8, 14))

    widgets = (frame, icon_label, text, title_label, detail_label, arrow)
    for widget in widgets:
        widget.bind("<Button-1>", lambda _event, fn=command: fn())
        widget.bind("<Enter>", lambda _event, f=frame: f.configure(highlightbackground=COLORS.border_strong))
        widget.bind("<Leave>", lambda _event, f=frame: f.configure(highlightbackground=COLORS.border))
    return frame


def empty_state(parent: tk.Widget, title: str, detail: str, icon: str = "○") -> tk.Frame:
    frame = tk.Frame(parent, bg=COLORS.surface)
    tk.Label(
        frame,
        text=icon,
        bg=COLORS.surface,
        fg=COLORS.text_subtle,
        font=(FONT["family"], 26),
    ).pack(pady=(28, 8))
    tk.Label(
        frame,
        text=title,
        bg=COLORS.surface,
        fg=COLORS.text,
        font=(FONT["family"], FONT["section"], "bold"),
    ).pack()
    tk.Label(
        frame,
        text=detail,
        bg=COLORS.surface,
        fg=COLORS.text_muted,
        font=(FONT["family"], FONT["body"]),
    ).pack(pady=(5, 28))
    return frame
