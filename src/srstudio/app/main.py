from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from srstudio import __version__
from srstudio.app.commands import CommandRegistry, StudioCommand
from srstudio.app.design import COLORS, FONT, NAVIGATION
from srstudio.app.encartes_view import EncartesStudioView
from srstudio.app.palette import CommandPalette
from srstudio.core.models import StudioProject
from srstudio.diagnostics.audit import ProjectAudit
from srstudio.intelligence.suggestions import SuggestionEngine
from srstudio.projects.session import ProjectSession
from srstudio.projects.store import ProjectStore
from srstudio.workflows.professional import ProfessionalWorkflow


class SRStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"SR Studio {__version__} Professional")
        self.geometry("1540x920")
        self.minsize(1220, 760)
        self.configure(bg=COLORS.bg)

        self.data_dir = Path.home() / ".srstudio5"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = ProjectStore(self.data_dir / "autosave")
        self.project = StudioProject(name="Novo Projeto SR")
        self.session = ProjectSession(self.project, self.store, self.data_dir / "autosave")
        self.workflow = ProfessionalWorkflow(self.project, self.session)
        self.audit = ProjectAudit()
        self.suggestions = SuggestionEngine()
        self.commands = CommandRegistry()
        self._active_nav = "Início"
        self._active_view: tk.Widget | None = None

        self._build_styles()
        self._build_shell()
        self._register_commands()
        self._bind_global_shortcuts()
        self._navigate("Início", self.show_home)
        self.after(15000, self._autosave_tick)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS.bg)
        style.configure("Surface.TFrame", background=COLORS.surface)
        style.configure("TLabel", background=COLORS.bg, foreground=COLORS.text, font=(FONT["family"], FONT["body"]))
        style.configure("Primary.TButton", background=COLORS.primary, foreground="white", padding=(16, 10), borderwidth=0)
        style.map("Primary.TButton", background=[("active", COLORS.primary_hover)])
        style.configure("Ghost.TButton", background=COLORS.surface, foreground=COLORS.primary, padding=(14, 9), bordercolor=COLORS.border)

    def _build_shell(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=COLORS.sidebar, width=224)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        brand = tk.Frame(self.sidebar, bg=COLORS.sidebar)
        brand.pack(fill="x", padx=20, pady=(24, 26))
        tk.Label(brand, text="SR", bg=COLORS.primary, fg="white", font=(FONT["family"], 20, "bold"), width=3).pack(side="left")
        tk.Label(brand, text="SR Studio 5.0", bg=COLORS.sidebar, fg="white", font=(FONT["family"], 14, "bold")).pack(side="left", padx=12)

        self.nav_buttons: dict[str, tk.Button] = {}
        for label, icon in NAVIGATION:
            command = self.show_encartes if label == "Encartes Studio" else self.show_home
            button = tk.Button(
                self.sidebar,
                text=f"  {icon}   {label}",
                anchor="w",
                command=lambda name=label, fn=command: self._navigate(name, fn),
                bg=COLORS.sidebar,
                fg="white",
                activebackground=COLORS.sidebar_active,
                activeforeground="white",
                bd=0,
                padx=14,
                pady=11,
                font=(FONT["family"], 10),
                cursor="hand2",
            )
            button.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[label] = button

        footer = tk.Frame(self.sidebar, bg=COLORS.sidebar_dark)
        footer.pack(side="bottom", fill="x", padx=14, pady=18)
        tk.Label(footer, text="✦ SR Studio Professional", bg=COLORS.sidebar_dark, fg="white", font=(FONT["family"], 9, "bold")).pack(anchor="w", padx=12, pady=(12, 5))
        self.footer_status = tk.Label(footer, text="Projeto protegido por autosave", bg=COLORS.sidebar_dark, fg="#DCE8FF", font=(FONT["family"], 8))
        self.footer_status.pack(anchor="w", padx=12, pady=(0, 12))

        self.main = tk.Frame(self, bg=COLORS.bg)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)
        topbar = tk.Frame(self.main, bg=COLORS.surface, height=68, highlightbackground=COLORS.border, highlightthickness=1)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        topbar.columnconfigure(1, weight=1)
        search = tk.Button(topbar, text="⌕  Buscar projetos, produtos, modelos...     Ctrl + K", anchor="w", command=self.open_palette, relief="flat", bg="#F7F9FC", fg=COLORS.text_muted, font=(FONT["family"], 10), padx=14)
        search.grid(row=0, column=0, padx=26, pady=16, ipadx=40, ipady=8, sticky="w")
        self.project_state = tk.Label(topbar, text="● Salvo", bg=COLORS.surface, fg=COLORS.success, font=(FONT["family"], 9, "bold"))
        self.project_state.grid(row=0, column=2, padx=12)
        tk.Label(topbar, text="SR  Administrador", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 10, "bold")).grid(row=0, column=3, padx=(4, 24))

        self.content = tk.Frame(self.main, bg=COLORS.bg)
        self.content.grid(row=1, column=0, sticky="nsew")

    def _register_commands(self) -> None:
        self.commands.extend(
            [
                StudioCommand("new-project", "Novo projeto", "Projeto", "Ctrl+N", ("criar", "novo"), self.new_project),
                StudioCommand("open-project", "Abrir projeto", "Projeto", "Ctrl+O", ("srproject", "abrir"), self.open_project),
                StudioCommand("save-project", "Salvar projeto", "Projeto", "Ctrl+S", ("salvar",), self.save_project),
                StudioCommand("import", "Importar Excel ou Canva/PPTX", "Importação", "Ctrl+I", ("excel", "xlsx", "pptx", "canva"), self.import_source),
                StudioCommand("encartes", "Abrir Encartes Studio", "Navegação", "Ctrl+2", ("editor", "encarte"), lambda: self._navigate("Encartes Studio", self.show_encartes)),
                StudioCommand("review", "Revisar campanha", "Qualidade", "Ctrl+R", ("validar", "erros", "qualidade"), self.review_project),
                StudioCommand("export", "Exportar campanha", "Exportação", "Ctrl+E", ("png", "impressao", "instagram"), self.export_project),
                StudioCommand("home", "Ir para início", "Navegação", "Ctrl+1", ("dashboard",), lambda: self._navigate("Início", self.show_home)),
            ]
        )

    def _bind_global_shortcuts(self) -> None:
        bindings = {
            "<Control-k>": self.open_palette,
            "<Control-n>": self.new_project,
            "<Control-o>": self.open_project,
            "<Control-s>": self.save_project,
            "<Control-i>": self.import_source,
            "<Control-e>": self.export_project,
            "<Control-Key-1>": lambda _e=None: self._navigate("Início", self.show_home),
            "<Control-Key-2>": lambda _e=None: self._navigate("Encartes Studio", self.show_encartes),
        }
        for sequence, handler in bindings.items():
            self.bind_all(sequence, handler)

    def open_palette(self, _event=None) -> str:
        CommandPalette(self, self.commands)
        return "break"

    def _navigate(self, name: str, fn) -> None:
        self._active_nav = name
        for label, button in self.nav_buttons.items():
            button.configure(bg=COLORS.sidebar_active if label == name else COLORS.sidebar)
        fn()

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def show_home(self) -> None:
        self._clear_content()
        audit = self.audit.inspect(self.project)
        container = tk.Frame(self.content, bg=COLORS.bg)
        container.pack(fill="both", expand=True, padx=28, pady=24)
        hero = self._card(container)
        hero.pack(fill="x", pady=(0, 16))
        left = tk.Frame(hero, bg=COLORS.surface)
        left.pack(side="left", fill="both", expand=True, padx=24, pady=22)
        tk.Label(left, text=self.project.name, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 24, "bold")).pack(anchor="w")
        tk.Label(left, text="Campanha profissional com autosave, validação e recuperação.", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 10)).pack(anchor="w", pady=(4, 14))
        actions = tk.Frame(left, bg=COLORS.surface)
        actions.pack(anchor="w")
        ttk.Button(actions, text="＋ Novo Projeto", style="Primary.TButton", command=self.new_project).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="▦ Importar", style="Ghost.TButton", command=self.import_source).pack(side="left", padx=8)
        ttk.Button(actions, text="▣ Abrir Editor", style="Ghost.TButton", command=lambda: self._navigate("Encartes Studio", self.show_encartes)).pack(side="left", padx=8)
        ttk.Button(actions, text="✓ Revisar", style="Ghost.TButton", command=self.review_project).pack(side="left", padx=8)

        metrics = tk.Frame(container, bg=COLORS.bg)
        metrics.pack(fill="x", pady=(0, 12))
        for col in range(5):
            metrics.columnconfigure(col, weight=1)
        values = [
            ("Produtos", str(audit.products)),
            ("Páginas", str(audit.pages)),
            ("Cards", str(audit.cards)),
            ("Qualidade", f"{audit.quality}/100"),
            ("Erros", str(audit.validation_errors)),
        ]
        for index, (title, value) in enumerate(values):
            card = self._card(metrics)
            card.grid(row=0, column=index, sticky="nsew", padx=5)
            tk.Label(card, text=value, bg=COLORS.surface, fg=COLORS.primary if title != "Erros" or audit.validation_errors == 0 else "#C62828", font=(FONT["family"], 20, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
            tk.Label(card, text=title, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 9)).pack(anchor="w", padx=16, pady=(0, 14))

        suggestion_card = self._card(container)
        suggestion_card.pack(fill="both", expand=True)
        tk.Label(suggestion_card, text="SR IA · Recomendações", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        suggestions = self.suggestions.suggest(self.project)[:6]
        if not suggestions:
            tk.Label(suggestion_card, text="Nenhuma recomendação no momento.", bg=COLORS.surface, fg=COLORS.text_muted).pack(anchor="w", padx=18, pady=12)
        for item in suggestions:
            row = tk.Frame(suggestion_card, bg="#F8FAFD")
            row.pack(fill="x", padx=18, pady=4)
            tk.Label(row, text=item.title, bg="#F8FAFD", fg=COLORS.text, font=(FONT["family"], 10, "bold")).pack(anchor="w", padx=12, pady=(8, 1))
            tk.Label(row, text=item.detail, bg="#F8FAFD", fg=COLORS.text_muted, font=(FONT["family"], 9)).pack(anchor="w", padx=12, pady=(0, 8))

    def show_encartes(self) -> None:
        self._clear_content()
        self._active_view = EncartesStudioView(self.content, self.project)

    def new_project(self, _event=None) -> str:
        if self.session.state.dirty and not messagebox.askyesno("Novo projeto", "Existem alterações não salvas. Criar um novo projeto mesmo assim?"):
            return "break"
        self._set_project(StudioProject(name="Novo Projeto SR"))
        self._navigate("Início", self.show_home)
        return "break"

    def open_project(self, _event=None) -> str:
        path = filedialog.askopenfilename(title="Abrir projeto SR", filetypes=[("Projeto SR", "*.srproject"), ("Todos", "*.*")])
        if not path:
            return "break"
        try:
            project = self.store.load(path)
            self._set_project(project)
            self.session.state.project_path = path
            self._navigate("Início", self.show_home)
        except Exception as exc:
            messagebox.showerror("Abrir projeto", f"Não foi possível abrir o projeto.\n\n{exc}")
        return "break"

    def save_project(self, _event=None) -> str:
        path = self.session.state.project_path
        if not path:
            path = filedialog.asksaveasfilename(title="Salvar projeto SR", defaultextension=".srproject", filetypes=[("Projeto SR", "*.srproject")])
        if not path:
            return "break"
        try:
            self.session.save(path)
            self._update_dirty_state()
        except Exception as exc:
            messagebox.showerror("Salvar projeto", f"Não foi possível salvar.\n\n{exc}")
        return "break"

    def import_source(self, _event=None) -> str:
        path = filedialog.askopenfilename(title="Importar para o SR Studio", filetypes=[("Excel / Canva", "*.xlsx *.xlsm *.pptx"), ("Todos", "*.*")])
        if not path:
            return "break"
        try:
            result = self.workflow.import_source(path)
            self._update_dirty_state()
            messagebox.showinfo("Importação concluída", result.message)
            self._navigate("Encartes Studio", self.show_encartes)
        except Exception as exc:
            messagebox.showerror("Importação", f"Não foi possível importar o arquivo.\n\n{exc}")
        return "break"

    def review_project(self, _event=None) -> str:
        result = self.workflow.review()
        quality = result.payload["quality"]
        summary = result.payload["summary"]
        messagebox.showinfo("Revisão da campanha", f"Qualidade: {quality.total}/100\nErros: {summary.get('error', 0)}\nAvisos: {summary.get('warning', 0)}")
        self.show_home()
        return "break"

    def export_project(self, _event=None) -> str:
        destination = filedialog.askdirectory(title="Pasta para exportação")
        if not destination:
            return "break"
        try:
            result = self.workflow.export(destination, "print")
            if not result.ok:
                messagebox.showwarning("Exportação bloqueada", result.message)
            else:
                messagebox.showinfo("Exportação", result.message)
        except Exception as exc:
            messagebox.showerror("Exportação", f"Não foi possível exportar.\n\n{exc}")
        return "break"

    def _set_project(self, project: StudioProject) -> None:
        self.project = project
        self.session = ProjectSession(project, self.store, self.data_dir / "autosave")
        self.workflow = ProfessionalWorkflow(project, self.session)
        self._update_dirty_state()

    def _autosave_tick(self) -> None:
        try:
            path = self.session.autosave()
            if path:
                self.footer_status.configure(text="Autosave atualizado")
        except Exception:
            self.footer_status.configure(text="⚠ Falha no autosave")
        finally:
            self.after(15000, self._autosave_tick)

    def _update_dirty_state(self) -> None:
        dirty = self.session.state.dirty
        self.project_state.configure(text="● Alterado" if dirty else "● Salvo", fg="#E69200" if dirty else COLORS.success)

    def _close(self) -> None:
        if self.session.state.dirty:
            self.session.autosave(force=True)
        self.destroy()

    @staticmethod
    def _card(parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)


def run() -> None:
    SRStudioApp().mainloop()


if __name__ == "__main__":
    run()
