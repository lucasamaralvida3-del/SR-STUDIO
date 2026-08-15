from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from srstudio import __version__
from srstudio.app.ai_view import SRIAView
from srstudio.app.commands import CommandRegistry, StudioCommand
from srstudio.app.design import COLORS, FONT, NAVIGATION
from srstudio.app.encartes_view import EncartesStudioView
from srstudio.app.export_view import ExportView
from srstudio.app.palette import CommandPalette
from srstudio.app.proof_view import ProofView
from srstudio.app.validation_view import ValidationView
from srstudio.assets.catalog import AssetCatalog
from srstudio.core.models import StudioProject
from srstudio.diagnostics.audit import ProjectAudit
from srstudio.diagnostics.crash_guard import CrashGuard
from srstudio.diagnostics.health import HealthCenter
from srstudio.images.quality import ImageQualityAnalyzer
from srstudio.intelligence.suggestions import SuggestionEngine
from srstudio.products.database import ProductDatabase
from srstudio.projects.package import ProjectPackage
from srstudio.projects.recent import RecentProjectsStore
from srstudio.projects.session import ProjectSession
from srstudio.projects.store import ProjectStore
from srstudio.templates.learning import LayoutLearningEngine
from srstudio.templates.registry import TemplateRegistry
from srstudio.workflows.professional import ProfessionalWorkflow


class SRStudioWorkspace(tk.Tk):
    """Shell oficial do SR Studio 5.0 Professional."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"SR Studio {__version__} Professional")
        self.geometry("1560x940")
        self.minsize(1240, 780)
        self.configure(bg=COLORS.bg)

        self.data_dir = Path.home() / ".srstudio5"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = ProjectStore(self.data_dir / "autosave")
        self.recent = RecentProjectsStore(self.data_dir / "recent-projects.json")
        self.assets = AssetCatalog(self.data_dir / "assets")
        self.product_db = ProductDatabase(self.data_dir / "products.sqlite3")
        self.crash_guard = CrashGuard(self.data_dir / "crashes", __version__)
        self.crash_guard.install(lambda: self.session.state.project_path if hasattr(self, "session") else "")
        self.audit = ProjectAudit()
        self.suggestions = SuggestionEngine()
        self.image_quality = ImageQualityAnalyzer()
        self.templates = TemplateRegistry()
        self.layout_learning = LayoutLearningEngine()
        self.commands = CommandRegistry()
        self.project = StudioProject(name="Novo Projeto SR")
        self._attach_project(self.project)
        self._active_nav = "Início"

        self._style()
        self._shell()
        self._register_commands()
        self._bind_shortcuts()
        self._offer_recovery()
        self.navigate("Início")
        self.after(12000, self._maintenance_tick)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _attach_project(self, project: StudioProject) -> None:
        self.project = project
        self.session = ProjectSession(project, self.store, self.data_dir / "autosave", autosave_interval=30)
        self.workflow = ProfessionalWorkflow(project, self.session)
        self.package = ProjectPackage(self.store)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS.bg)
        style.configure("TLabel", background=COLORS.bg, foreground=COLORS.text, font=(FONT["family"], 10))
        style.configure("Primary.TButton", background=COLORS.primary, foreground="white", padding=(15, 9), borderwidth=0)
        style.map("Primary.TButton", background=[("active", COLORS.primary_hover)])
        style.configure("Ghost.TButton", background=COLORS.surface, foreground=COLORS.primary, padding=(13, 8), bordercolor=COLORS.border)

    def _shell(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.sidebar = tk.Frame(self, bg=COLORS.sidebar, width=224)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        brand = tk.Frame(self.sidebar, bg=COLORS.sidebar)
        brand.pack(fill="x", padx=18, pady=(22, 24))
        logo = tk.Label(brand, text="SR", width=3, bg="white", fg=COLORS.sidebar, font=(FONT["family"], 19, "bold"))
        logo.pack(side="left", ipady=6)
        tk.Label(brand, text="SR Studio", bg=COLORS.sidebar, fg="white", font=(FONT["family"], 14, "bold")).pack(side="left", padx=11)

        self.nav_buttons: dict[str, tk.Button] = {}
        for label, icon in NAVIGATION:
            button = tk.Button(
                self.sidebar,
                text=f"  {icon}   {label}",
                anchor="w",
                command=lambda name=label: self.navigate(name),
                bg=COLORS.sidebar,
                fg="white",
                activebackground=COLORS.sidebar_active,
                activeforeground="white",
                bd=0,
                padx=14,
                pady=10,
                font=(FONT["family"], 9),
                cursor="hand2",
            )
            button.pack(fill="x", padx=11, pady=2)
            self.nav_buttons[label] = button

        footer = tk.Frame(self.sidebar, bg=COLORS.sidebar_dark)
        footer.pack(side="bottom", fill="x", padx=12, pady=14)
        tk.Label(footer, text=f"Professional  {__version__}", bg=COLORS.sidebar_dark, fg="white", font=(FONT["family"], 8, "bold")).pack(anchor="w", padx=11, pady=(10, 3))
        self.sidebar_status = tk.Label(footer, text="Autosave ativo", bg=COLORS.sidebar_dark, fg="#D7E4FF", font=(FONT["family"], 8))
        self.sidebar_status.pack(anchor="w", padx=11, pady=(0, 10))

        self.main = tk.Frame(self, bg=COLORS.bg)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)
        topbar = tk.Frame(self.main, bg=COLORS.surface, height=66, highlightbackground=COLORS.border, highlightthickness=1)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        topbar.columnconfigure(1, weight=1)
        tk.Button(
            topbar,
            text="⌕  Buscar comandos, produtos, projetos...     Ctrl + K",
            anchor="w",
            command=self.open_palette,
            relief="flat",
            bg="#F6F8FC",
            fg=COLORS.text_muted,
            font=(FONT["family"], 9),
            padx=14,
        ).grid(row=0, column=0, padx=24, pady=15, ipadx=48, ipady=7, sticky="w")
        self.dirty_label = tk.Label(topbar, text="● Salvo", bg=COLORS.surface, fg=COLORS.success, font=(FONT["family"], 9, "bold"))
        self.dirty_label.grid(row=0, column=2, padx=14)
        tk.Label(topbar, text="SR  Administrador", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 9, "bold")).grid(row=0, column=3, padx=(0, 22))
        self.content = tk.Frame(self.main, bg=COLORS.bg)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.bind("<<SRProjectChanged>>", lambda _e: self._refresh_dirty())

    def _register_commands(self) -> None:
        commands = (
            StudioCommand("project.new", "Novo projeto", "Projeto", "Ctrl+N", ("novo", "criar"), self.new_project),
            StudioCommand("project.open", "Abrir projeto", "Projeto", "Ctrl+O", ("srproject", "srpack"), self.open_project),
            StudioCommand("project.save", "Salvar projeto", "Projeto", "Ctrl+S", ("salvar",), self.save_project),
            StudioCommand("project.package", "Criar pacote portátil SR", "Projeto", "", ("srpack", "portatil", "backup"), self.create_portable_package),
            StudioCommand("import.source", "Importar Excel ou Canva/PPTX", "Importação", "Ctrl+I", ("xlsx", "pptx", "canva"), self.import_source),
            StudioCommand("view.editor", "Abrir Encartes Studio", "Navegação", "Ctrl+2", ("editor",), lambda: self.navigate("Encartes Studio")),
            StudioCommand("view.ai", "Abrir SR IA", "Navegação", "Ctrl+3", ("ia", "assistente"), lambda: self.navigate("SR IA")),
            StudioCommand("view.validation", "Abrir validação", "Navegação", "Ctrl+4", ("qualidade", "erros"), lambda: self.navigate("Validação")),
            StudioCommand("view.proof", "Abrir Modo Prova", "Qualidade", "Ctrl+5", ("aprovar", "revisar paginas"), self.show_proof),
            StudioCommand("view.export", "Abrir exportação", "Navegação", "Ctrl+6", ("pdf", "png", "instagram"), lambda: self.navigate("Exportação")),
            StudioCommand("layout.learn", "Aprender layout da página atual", "Modelos", "", ("template", "padrao"), self.learn_current_layout),
            StudioCommand("project.review", "Revisar campanha", "Qualidade", "Ctrl+R", ("preflight", "validar"), lambda: self.navigate("Validação")),
        )
        self.commands.extend(commands)

    def _bind_shortcuts(self) -> None:
        bindings = {
            "<Control-k>": self.open_palette,
            "<Control-n>": self.new_project,
            "<Control-o>": self.open_project,
            "<Control-s>": self.save_project,
            "<Control-i>": self.import_source,
            "<Control-Key-1>": lambda _e=None: self.navigate("Início"),
            "<Control-Key-2>": lambda _e=None: self.navigate("Encartes Studio"),
            "<Control-Key-3>": lambda _e=None: self.navigate("SR IA"),
            "<Control-Key-4>": lambda _e=None: self.navigate("Validação"),
            "<Control-Key-5>": lambda _e=None: self.show_proof(),
            "<Control-Key-6>": lambda _e=None: self.navigate("Exportação"),
        }
        for sequence, handler in bindings.items():
            self.bind_all(sequence, handler)

    def navigate(self, name: str) -> None:
        self._active_nav = name
        for label, button in self.nav_buttons.items():
            button.configure(bg=COLORS.sidebar_active if label == name else COLORS.sidebar)
        self._clear()
        factories = {
            "Início": self._home,
            "Central 5.0": self._central,
            "Encartes Studio": lambda: EncartesStudioView(self.content, self.project),
            "Banco de Produtos": self._products_view,
            "Planilhas": self._imports_view,
            "Modelos": self._templates_view,
            "Validação": lambda: ValidationView(self.content, self.project),
            "Exportação": lambda: ExportView(self.content, self.project),
            "SR IA": lambda: SRIAView(self.content, self.project, self._mark_changed),
            "Configurações": self._settings_view,
        }
        factories.get(name, self._home)()

    def _clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def _home(self) -> None:
        audit = self.audit.inspect(self.project)
        root = tk.Frame(self.content, bg=COLORS.bg)
        root.pack(fill="both", expand=True, padx=28, pady=24)
        hero = self._card(root)
        hero.pack(fill="x", pady=(0, 14))
        tk.Label(hero, text=self.project.name, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 24, "bold")).pack(anchor="w", padx=22, pady=(20, 4))
        tk.Label(hero, text="Crie, revise e exporte campanhas em um único fluxo profissional.", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 10)).pack(anchor="w", padx=22)
        buttons = tk.Frame(hero, bg=COLORS.surface)
        buttons.pack(anchor="w", padx=22, pady=18)
        ttk.Button(buttons, text="Importar campanha", style="Primary.TButton", command=self.import_source).pack(side="left")
        ttk.Button(buttons, text="Abrir editor", style="Ghost.TButton", command=lambda: self.navigate("Encartes Studio")).pack(side="left", padx=7)
        ttk.Button(buttons, text="SR IA", style="Ghost.TButton", command=lambda: self.navigate("SR IA")).pack(side="left", padx=7)
        ttk.Button(buttons, text="Modo Prova", style="Ghost.TButton", command=self.show_proof).pack(side="left", padx=7)
        metrics = tk.Frame(root, bg=COLORS.bg)
        metrics.pack(fill="x", pady=(0, 12))
        data = (("Produtos", audit.products), ("Páginas", audit.pages), ("Cards", audit.cards), ("Qualidade", f"{audit.quality}/100"), ("Erros", audit.validation_errors))
        for index, (title, value) in enumerate(data):
            metrics.columnconfigure(index, weight=1)
            card = self._card(metrics)
            card.grid(row=0, column=index, sticky="nsew", padx=4)
            color = COLORS.danger if title == "Erros" and int(value) else COLORS.primary
            tk.Label(card, text=str(value), bg=COLORS.surface, fg=color, font=(FONT["family"], 19, "bold")).pack(anchor="w", padx=14, pady=(12, 1))
            tk.Label(card, text=title, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(anchor="w", padx=14, pady=(0, 12))
        self._recommendations(root)
        self._recent_projects(root)

    def _central(self) -> None:
        audit = self.audit.inspect(self.project)
        root = self._section("Central 5.0", "Visão técnica e operacional do projeto atual.")
        rows = (
            ("Integridade do projeto", "OK" if audit.validation_errors == 0 else f"{audit.validation_errors} erro(s)"),
            ("Pronto para exportar", "SIM" if audit.ready_to_export else "NÃO"),
            ("Produtos sem imagem", str(audit.missing_images)),
            ("Produtos não utilizados", str(audit.orphan_products)),
            ("Autosave", "ATIVO"),
            ("Canal", "Development"),
        )
        for title, value in rows:
            row = tk.Frame(root, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=title, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 9, "bold")).pack(side="left", padx=14, pady=10)
            tk.Label(row, text=value, bg=COLORS.surface, fg=COLORS.primary, font=(FONT["family"], 9, "bold")).pack(side="right", padx=14)

    def _products_view(self) -> None:
        root = self._section("Banco de Produtos", "Produtos carregados no projeto e biblioteca local.")
        for product in self.project.products[:200]:
            row = tk.Frame(root, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=product.name, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 9, "bold"), anchor="w").pack(side="left", fill="x", expand=True, padx=12, pady=8)
            image_state = "Imagem ✓" if product.has_image else "Sem imagem"
            tk.Label(row, text=f"{product.price or ''}  /{product.unit}   {image_state}", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(side="right", padx=12)

    def _imports_view(self) -> None:
        root = self._section("Planilhas e Importação", "Excel, XLSM e projetos Canva exportados como PPTX.")
        ttk.Button(root, text="Importar Excel / PPTX", style="Primary.TButton", command=self.import_source).pack(anchor="w", pady=10)
        source = self.project.settings.get("pptx_source")
        if source:
            tk.Label(root, text=f"Último PPTX: {source}", bg=COLORS.surface, fg=COLORS.text_muted, wraplength=800, justify="left").pack(anchor="w", pady=8)

    def _templates_view(self) -> None:
        root = self._section("Modelos", "Templates nativos e layouts aprendidos a partir das suas páginas.")
        ttk.Button(root, text="Aprender layout da página atual", style="Primary.TButton", command=self.learn_current_layout).pack(anchor="w", pady=10)
        for template in self.templates.all():
            tk.Label(root, text=f"▤  {template.name}", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 9, "bold")).pack(anchor="w", pady=3)

    def _settings_view(self) -> None:
        root = self._section("Configurações", "Preferências, pastas e infraestrutura local do SR Studio.")
        rows = (("Dados locais", str(self.data_dir)), ("Autosave", "30 segundos"), ("Versão", __version__), ("Modo", "Professional / Development"))
        for title, value in rows:
            tk.Label(root, text=f"{title}: {value}", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 9)).pack(anchor="w", pady=5)

    def show_proof(self) -> str:
        self._clear()
        ProofView(self.content, self.project, self._mark_changed)
        return "break"

    def open_palette(self, _event=None) -> str:
        CommandPalette(self, self.commands)
        return "break"

    def new_project(self, _event=None) -> str:
        self.session.refresh_dirty()
        if self.session.state.dirty and not messagebox.askyesno("Novo projeto", "Existem alterações não salvas. Criar outro projeto?"):
            return "break"
        self._attach_project(StudioProject(name="Novo Projeto SR"))
        self.navigate("Início")
        return "break"

    def open_project(self, _event=None) -> str:
        path = filedialog.askopenfilename(filetypes=[("Projeto SR", "*.srproject *.srpack"), ("Todos", "*.*")])
        if not path:
            return "break"
        try:
            source = Path(path)
            if source.suffix.lower() == ".srpack":
                unpack_dir = self.data_dir / "packages" / source.stem
                project = self.package.extract(source, unpack_dir)
                project_path = ""
            else:
                project = self.store.load(source)
                project_path = str(source)
            self._attach_project(project)
            self.session.state.project_path = project_path
            if project_path:
                self.recent.touch(project_path, project.name)
            self.navigate("Início")
        except Exception as exc:
            messagebox.showerror("Abrir projeto", f"Não foi possível abrir.\n\n{exc}")
        return "break"

    def save_project(self, _event=None) -> str:
        path = self.session.state.project_path
        if not path:
            path = filedialog.asksaveasfilename(defaultextension=".srproject", filetypes=[("Projeto SR", "*.srproject")])
        if not path:
            return "break"
        try:
            saved = self.session.save(path)
            self.recent.touch(saved, self.project.name)
            self._refresh_dirty()
        except Exception as exc:
            messagebox.showerror("Salvar projeto", f"Não foi possível salvar.\n\n{exc}")
        return "break"

    def create_portable_package(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".srpack", filetypes=[("Pacote SR", "*.srpack")])
        if path:
            try:
                result = self.package.create(self.project, path)
                messagebox.showinfo("Pacote criado", str(result))
            except Exception as exc:
                messagebox.showerror("Pacote portátil", str(exc))

    def import_source(self, _event=None) -> str:
        path = filedialog.askopenfilename(filetypes=[("Excel / Canva PPTX", "*.xlsx *.xlsm *.pptx"), ("Todos", "*.*")])
        if not path:
            return "break"
        try:
            result = self.workflow.import_source(path)
            messagebox.showinfo("Importação", result.message)
            self.navigate("Encartes Studio")
            self._refresh_dirty()
        except Exception as exc:
            messagebox.showerror("Importação", f"Falha na importação.\n\n{exc}")
        return "break"

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
                    {"x": slot.x, "y": slot.y, "width": slot.width, "height": slot.height, "role": slot.role}
                    for slot in template.slots
                ],
            }
        )
        self._mark_changed()
        messagebox.showinfo("Layout aprendido", f"'{template.name}' salvo no projeto com {len(template.slots)} slot(s).")

    def _offer_recovery(self) -> None:
        candidates = self.store.recovery_candidates()
        if self.crash_guard.should_offer_safe_mode() and candidates:
            if messagebox.askyesno("Recuperação do SR Studio", "A execução anterior terminou inesperadamente. Restaurar o autosave mais recente?"):
                try:
                    self._attach_project(self.store.load(candidates[0]))
                except Exception:
                    pass
            self.crash_guard.clear()

    def _maintenance_tick(self) -> None:
        try:
            path = self.session.autosave()
            self.session.refresh_dirty()
            self.sidebar_status.configure(text="Autosave atualizado" if path else "Autosave ativo")
            self._refresh_dirty()
        except Exception:
            self.sidebar_status.configure(text="⚠ Autosave com falha")
        finally:
            self.after(12000, self._maintenance_tick)

    def _refresh_dirty(self) -> None:
        dirty = self.session.refresh_dirty()
        self.dirty_label.configure(text="● Alterado" if dirty else "● Salvo", fg=COLORS.warning if dirty else COLORS.success)

    def _mark_changed(self) -> None:
        self.session.mark_dirty()
        self._refresh_dirty()

    def _recommendations(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        tk.Label(card, text="✦ SR IA · Próximas ações", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 12, "bold")).pack(anchor="w", padx=16, pady=(14, 7))
        for item in self.suggestions.suggest(self.project)[:4]:
            tk.Label(card, text=f"• {item.title} — {item.detail}", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8), wraplength=980, justify="left").pack(anchor="w", padx=16, pady=3)
        tk.Frame(card, bg=COLORS.surface, height=8).pack()

    def _recent_projects(self, parent: tk.Widget) -> None:
        items = self.recent.remove_missing()[:5]
        if not items:
            return
        card = self._card(parent)
        card.pack(fill="x")
        tk.Label(card, text="Projetos recentes", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 12, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
        for item in items:
            tk.Label(card, text=f"{item.name}   ·   {item.path}", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8), anchor="w").pack(fill="x", padx=16, pady=3)
        tk.Frame(card, bg=COLORS.surface, height=8).pack()

    def _section(self, title: str, subtitle: str) -> tk.Frame:
        root = tk.Frame(self.content, bg=COLORS.bg)
        root.pack(fill="both", expand=True, padx=28, pady=24)
        tk.Label(root, text=title, bg=COLORS.bg, fg=COLORS.text, font=(FONT["family"], 24, "bold")).pack(anchor="w")
        tk.Label(root, text=subtitle, bg=COLORS.bg, fg=COLORS.text_muted, font=(FONT["family"], 10)).pack(anchor="w", pady=(4, 14))
        body = self._card(root)
        body.pack(fill="both", expand=True, padx=0, pady=0)
        return body

    @staticmethod
    def _card(parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)

    def _close(self) -> None:
        try:
            self.session.autosave(force=True)
            self.crash_guard.clear()
            self.crash_guard.uninstall()
        finally:
            self.destroy()


def run() -> None:
    SRStudioWorkspace().mainloop()


if __name__ == "__main__":
    run()
