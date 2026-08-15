from __future__ import annotations

import tkinter as tk

from srstudio import __version__
from srstudio.app.design import COLORS, FONT, PAGE_META
from srstudio.app.encartes_professional_view import ProfessionalEncartesStudioView
from srstudio.app.workspace import SRStudioWorkspace


class SRStudioProfessional(SRStudioWorkspace):
    """Entrada visual profissional do SR Studio 5."""

    def navigate(self, name: str) -> None:
        if name != "Encartes Studio":
            super().navigate(name)
            return

        self._active_nav = name
        for label, button in self.nav_buttons.items():
            active = label == name
            button.configure(
                bg=COLORS.sidebar_active if active else COLORS.sidebar,
                fg="white" if active else COLORS.sidebar_text,
                font=(FONT["family"], FONT["small"], "bold" if active else "normal"),
            )
            self.nav_indicators[label].configure(bg="#77A7FF" if active else COLORS.sidebar)

        title, subtitle = PAGE_META[name]
        self.topbar_title.configure(text=title)
        self.topbar_subtitle.configure(text=subtitle)
        self._clear()
        ProfessionalEncartesStudioView(self.content, self.project)


def _show_splash(app: SRStudioProfessional) -> None:
    app.withdraw()
    splash = tk.Toplevel(app)
    splash.overrideredirect(True)
    splash.configure(bg=COLORS.sidebar)
    splash.attributes("-topmost", True)

    width, height = 520, 300
    app.update_idletasks()
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")

    shell = tk.Frame(
        splash,
        bg=COLORS.sidebar,
        highlightbackground="#245392",
        highlightthickness=1,
    )
    shell.pack(fill="both", expand=True)

    logo = tk.Label(
        shell,
        text="SR",
        bg=COLORS.primary,
        fg="white",
        font=(FONT["family"], 27, "bold"),
        padx=15,
        pady=11,
    )
    logo.pack(pady=(48, 16))
    tk.Label(
        shell,
        text="SR Studio",
        bg=COLORS.sidebar,
        fg="white",
        font=(FONT["family"], 21, "bold"),
    ).pack()
    tk.Label(
        shell,
        text="PROFESSIONAL",
        bg=COLORS.sidebar,
        fg=COLORS.sidebar_muted,
        font=(FONT["family"], 8, "bold"),
    ).pack(pady=(3, 18))

    progress_shell = tk.Frame(shell, bg="#17447E", width=280, height=4)
    progress_shell.pack()
    progress_shell.pack_propagate(False)
    progress = tk.Frame(progress_shell, bg="#78A8FF", width=205, height=4)
    progress.pack(side="left", fill="y")

    tk.Label(
        shell,
        text="Preparando seu workspace...",
        bg=COLORS.sidebar,
        fg=COLORS.sidebar_muted,
        font=(FONT["family"], FONT["small"]),
    ).pack(pady=(10, 2))
    tk.Label(
        shell,
        text=f"v{__version__}",
        bg=COLORS.sidebar,
        fg="#7196C7",
        font=(FONT["family"], FONT["micro"]),
    ).pack()

    def finish() -> None:
        if splash.winfo_exists():
            splash.destroy()
        app.deiconify()
        app.lift()
        app.focus_force()

    app.after(950, finish)


def run() -> None:
    app = SRStudioProfessional()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
