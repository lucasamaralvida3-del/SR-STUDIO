from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable

from srstudio.app.design import COLORS, FONT


class Tooltip:
    """Tooltip leve e reutilizável para ações do Studio."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 420) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event=None) -> None:
        self.hide()
        self._job = self.widget.after(self.delay, self.show)

    def show(self) -> None:
        if not self.text or not self.widget.winfo_exists():
            return
        self._job = None
        tip = tk.Toplevel(self.widget)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 7
        tip.geometry(f"+{x}+{y}")
        shell = tk.Frame(tip, bg=COLORS.text, padx=1, pady=1)
        shell.pack()
        tk.Label(
            shell,
            text=self.text,
            bg=COLORS.text,
            fg="white",
            font=(FONT["family"], FONT["micro"]),
            padx=8,
            pady=5,
        ).pack()
        self._tip = tip

    def hide(self, _event=None) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


@dataclass(frozen=True, slots=True)
class ToastStyle:
    background: str
    foreground: str
    accent: str


TOAST_STYLES = {
    "info": ToastStyle(COLORS.info_soft, COLORS.text, COLORS.info),
    "success": ToastStyle(COLORS.success_soft, COLORS.text, COLORS.success),
    "warning": ToastStyle(COLORS.warning_soft, COLORS.text, COLORS.warning),
    "danger": ToastStyle(COLORS.danger_soft, COLORS.text, COLORS.danger),
}


class ToastManager:
    """Notificações não bloqueantes dentro da janela principal."""

    def __init__(self, master: tk.Misc) -> None:
        self.master = master
        self.active: list[tk.Toplevel] = []

    def show(self, message: str, tone: str = "info", duration: int = 3200) -> None:
        style = TOAST_STYLES.get(tone, TOAST_STYLES["info"])
        toast = tk.Toplevel(self.master)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=COLORS.border_strong)

        body = tk.Frame(toast, bg=style.background, highlightbackground=COLORS.border, highlightthickness=1)
        body.pack(fill="both", expand=True)
        tk.Frame(body, bg=style.accent, width=4).pack(side="left", fill="y")
        tk.Label(
            body,
            text=message,
            bg=style.background,
            fg=style.foreground,
            font=(FONT["family"], FONT["small"]),
            justify="left",
            wraplength=330,
            padx=12,
            pady=10,
        ).pack(side="left", fill="both", expand=True)
        close = tk.Button(
            body,
            text="×",
            command=toast.destroy,
            bg=style.background,
            activebackground=style.background,
            fg=COLORS.text_muted,
            bd=0,
            font=(FONT["family"], 11),
            cursor="hand2",
        )
        close.pack(side="right", padx=(3, 8))

        self.active.append(toast)
        toast.bind("<Destroy>", lambda _e, item=toast: self._forget(item), add="+")
        self._reposition()
        toast.after(duration, lambda: toast.winfo_exists() and toast.destroy())

    def _forget(self, toast: tk.Toplevel) -> None:
        if toast in self.active:
            self.active.remove(toast)
        self._reposition()

    def _reposition(self) -> None:
        self.master.update_idletasks()
        base_x = self.master.winfo_rootx() + self.master.winfo_width() - 390
        base_y = self.master.winfo_rooty() + 92
        for index, toast in enumerate(self.active[-4:]):
            if toast.winfo_exists():
                toast.geometry(f"360x58+{base_x}+{base_y + index * 66}")


class IconButton(tk.Canvas):
    """Botão compacto com ícone vetorial desenhado no próprio Tk."""

    def __init__(
        self,
        master: tk.Widget,
        icon: str,
        command: Callable[[], None],
        tooltip: str = "",
        size: int = 32,
        accent: bool = False,
    ) -> None:
        self.size = size
        self.icon = icon
        self.command = command
        self.accent = accent
        bg = COLORS.primary_soft if accent else COLORS.surface_alt
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Button-1>", lambda _e: self.command())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        if tooltip:
            Tooltip(self, tooltip)
        self.redraw()

    def _set_hover(self, value: bool) -> None:
        bg = COLORS.primary_soft_hover if self.accent else COLORS.surface_pressed if value else COLORS.surface_alt
        if self.accent and not value:
            bg = COLORS.primary_soft
        self.configure(bg=bg)
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        color = COLORS.primary if self.accent else COLORS.text_muted
        c = self.size / 2
        s = self.size * 0.26
        w = 1.7
        if self.icon == "undo":
            self.create_arc(c - s, c - s, c + s, c + s, start=45, extent=230, style="arc", outline=color, width=2)
            self.create_line(c - s, c - 1, c - s + 6, c - 7, fill=color, width=2)
        elif self.icon == "redo":
            self.create_arc(c - s, c - s, c + s, c + s, start=-95, extent=230, style="arc", outline=color, width=2)
            self.create_line(c + s, c - 1, c + s - 6, c - 7, fill=color, width=2)
        elif self.icon == "layers":
            for offset in (-5, 0, 5):
                self.create_polygon(c, c - 8 + offset, c + 10, c - 3 + offset, c, c + 2 + offset, c - 10, c - 3 + offset, outline=color, fill="", width=1)
        elif self.icon == "grid":
            for dx in (-7, 0, 7):
                self.create_line(c + dx, c - 9, c + dx, c + 9, fill=color, width=w)
            for dy in (-7, 0, 7):
                self.create_line(c - 9, c + dy, c + 9, c + dy, fill=color, width=w)
        elif self.icon == "lock":
            self.create_rectangle(c - 8, c - 1, c + 8, c + 10, outline=color, width=2)
            self.create_arc(c - 6, c - 10, c + 6, c + 4, start=0, extent=180, style="arc", outline=color, width=2)
        elif self.icon == "delete":
            self.create_rectangle(c - 6, c - 5, c + 6, c + 9, outline=color, width=2)
            self.create_line(c - 9, c - 8, c + 9, c - 8, fill=color, width=2)
            self.create_line(c - 4, c - 11, c + 4, c - 11, fill=color, width=2)
        elif self.icon == "front":
            self.create_rectangle(c - 8, c - 5, c + 5, c + 8, outline=color, width=2)
            self.create_rectangle(c - 3, c - 10, c + 10, c + 3, outline=color, width=2)
        elif self.icon == "back":
            self.create_rectangle(c - 3, c - 10, c + 10, c + 3, outline=color, width=2)
            self.create_rectangle(c - 8, c - 5, c + 5, c + 8, outline=color, width=2)
        elif self.icon == "rotate":
            self.create_arc(c - 9, c - 9, c + 9, c + 9, start=35, extent=280, style="arc", outline=color, width=2)
            self.create_polygon(c + 7, c - 9, c + 11, c - 3, c + 4, c - 3, fill=color)
        elif self.icon == "star":
            points = []
            import math

            for index in range(10):
                radius = 10 if index % 2 == 0 else 4
                angle = -math.pi / 2 + index * math.pi / 5
                points.extend((c + math.cos(angle) * radius, c + math.sin(angle) * radius))
            self.create_polygon(*points, outline=color, fill="", width=2)
        elif self.icon == "align":
            self.create_line(c, c - 10, c, c + 10, fill=color, width=1)
            for width, y in ((16, -6), (10, 0), (18, 6)):
                self.create_line(c - width / 2, c + y, c + width / 2, c + y, fill=color, width=2)
        else:
            self.create_oval(c - 3, c - 3, c + 3, c + 3, fill=color, outline="")
