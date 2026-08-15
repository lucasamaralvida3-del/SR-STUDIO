from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from srstudio import __version__
from srstudio.app.design import COLORS, FONT, PAGE_META
from srstudio.app.editor_experience import StudioEditorExperience
from srstudio.app.ui_kit import ToastManager, Tooltip
from srstudio.app.workspace import SRStudioWorkspace


class SRStudioProfessional(SRStudioWorkspace):
    """Entrada visual profissional do SR Studio 5."""

    def __init__(self) -> None:
        super().__init__()
        self.toast = ToastManager(self)
        for label, button in self.nav_buttons.items():
            Tooltip(button, PAGE_META[label][1], delay=520)

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
        StudioEditorExperience(self.content, self.project)

    def save_project(self, _event=None) -> str:
        path = self.session.state.project_path
        if not path:
            path = filedialog.asksaveasfilename(
                defaultextension=".srproject",
                filetypes=[("Projeto SR", "*.srproject")],
            )
        if not path:
            return "break"
        try:
            saved = self.session.save(path)
            self.recent.touch(saved, self.project.name)
            self._refresh_dirty()
            self.toast.show("Projeto salvo com segurança.", "success")
        except Exception as exc:
            messagebox.showerror("Salvar projeto", f"Não foi possível salvar.\n\n{exc}")
        return "break"

    def import_source(self, _event=None) -> str:
        path = filedialog.askopenfilename(
            filetypes=[("Excel / Canva PPTX", "*.xlsx *.xlsm *.pptx"), ("Todos", "*.*")]
        )
        if not path:
            return "break"
        try:
            result = self.workflow.import_source(path)
            self.navigate("Encartes Studio")
            self._refresh_dirty()
            self.toast.show(result.message or "Importação concluída.", "success", 4200)
        except Exception as exc:
            messagebox.showerror("Importação", f"Falha na importação.\n\n{exc}")
        return "break"

    def create_portable_package(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".srpack",
            filetypes=[("Pacote SR", "*.srpack")],
        )
        if not path:
            return
        try:
            result = self.package.create(self.project, path)
            self.toast.show(f"Pacote portátil criado: {Path(result).name}", "success", 4200)
        except Exception as exc:
            messagebox.showerror("Pacote portátil", str(exc))

    def learn_current_layout(self) -> None:
        page = self.project.pages[0]
        template = self.layout_learning.learn_page(page, f"SR {page.name}")
        learned = self.project.settings.setdefault("learned_templates", [])
        learned.append(
            {
                "name": template.name,
                "page_width": template.page_width,
                "page_height": template.page_height,
                "background": template.background,
                "metadata": template.metadata,
                "slots": [
                    {
                        "x": slot.x,
                        "y": slot.y,
                        "width": slot.width,
                        "height": slot.height,
                        "role": slot.role,
                    }
                    for slot in template.slots
                ],
            }
        )
        self._mark_changed()
        self.toast.show(
            f"Layout '{template.name}' aprendido com {len(template.slots)} slot(s).",
            "success",
            4200,
        )


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
    progress = tk.Frame(progress_shell, bg="#78A8FF", width=60, height=4)
    progress.pack(side="left", fill="y")

    status = tk.Label(
        shell,
        text="Carregando núcleo...",
        bg=COLORS.sidebar,
        fg=COLORS.sidebar_muted,
        font=(FONT["family"], FONT["small"]),
    )
    status.pack(pady=(10, 2))
    tk.Label(
        shell,
        text=f"v{__version__}",
        bg=COLORS.sidebar,
        fg="#7196C7",
        font=(FONT["family"], FONT["micro"]),
    ).pack()

    stages = (
        (160, 110, "Preparando projetos..."),
        (360, 185, "Carregando editor visual..."),
        (590, 245, "Inicializando SR IA..."),
        (780, 280, "Workspace pronto"),
    )
    for delay, width_value, text in stages:
        app.after(
            delay,
            lambda w=width_value, label=text: (progress.configure(width=w), status.configure(text=label)),
        )

    def finish() -> None:
        if splash.winfo_exists():
            splash.destroy()
        app.deiconify()
        app.lift()
        app.focus_force()
        app.after(300, lambda: app.toast.show("SR Studio pronto para trabalhar.", "success", 2200))

    app.after(980, finish)


def run() -> None:
    app = SRStudioProfessional()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
